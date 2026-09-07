from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .campaign import read_manifest

METRICS = {
    "molecules/unit cell": "molecules_per_unit_cell",
    "mol/kg framework": "mol_per_kg",
    "milligram/gram framework": "mg_per_g",
    "cm^3 (STP)/gr framework": "cm3_stp_per_g",
    "cm^3 (STP)/cm^3 framework": "cm3_stp_per_cm3",
}


def parse_gcmc(path: str | Path, component_count: int) -> list[dict[str, float | None]]:
    records = [{f"{kind}_{label}": None for kind in ("absolute", "excess") for label in METRICS.values()}
               | {"qst_kj_mol": None} for _ in range(component_count)]
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    component_index = 0
    for line in lines:
        kind = "absolute" if "Average loading absolute" in line else "excess" if "Average loading excess" in line else None
        if kind is None or component_index >= component_count:
            continue
        for source, label in METRICS.items():
            if source in line:
                records[component_index][f"{kind}_{label}"] = float(line.split("+/-", 1)[0].split()[-1])
                if kind == "excess" and source == "cm^3 (STP)/cm^3 framework":
                    component_index += 1
                break
    for offset, line in enumerate(lines):
        match = re.match(r"\s*Enthalpy of adsorption component (\d+)", line)
        if not match:
            continue
        component = int(match.group(1))
        if component >= component_count:
            continue
        for candidate in lines[offset + 1:offset + 31]:
            if "[KJ/MOL]" in candidate:
                records[component]["qst_kj_mol"] = float(candidate.split()[0])
                break
    return records


def extract_energy_trace(path: str | Path) -> list[tuple[int, float]]:
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    result = []
    for index, line in enumerate(lines):
        if "Current cycle:" not in line or "[Init]" in line or "Average Properties" in line:
            continue
        for candidate in lines[index + 1:]:
            if "Current total potential energy:" in candidate:
                result.append((len(result) + 1, float(candidate.split()[4])))
                break
            if "Current cycle:" in candidate:
                break
    return result


def extract_pdb_model(source: Path, model_number: int, destination: Path) -> bool:
    wanted = f"MODEL{model_number:>5}"
    selected: list[str] = []
    active = False
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True):
        if line.startswith(wanted):
            active = True
        if active:
            selected.append(line)
            if line.startswith("ENDMDL"):
                break
    if not selected:
        return False
    destination.write_text("".join(selected), encoding="utf-8")
    return True


def collect(run_dir: str | Path, results_root: str | Path) -> dict[str, int]:
    run_dir = Path(run_dir).resolve()
    cfg = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    output_dir = Path(results_root).resolve() / cfg["workflow"] / cfg["campaign"]
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = read_manifest(run_dir)
    states = {}
    for path in (run_dir / "state").glob("*.json"):
        if not path.stem.isdigit():
            continue
        state = json.loads(path.read_text(encoding="utf-8"))
        states[int(state["array_index"])] = state

    if cfg["workflow"] != "minimization":
        fieldnames = [
            "campaign", "workflow", "task_id", "status", "framework", "temperature", "pressure",
            "component_index", "component", "mole_fraction", "absolute_molecules_per_unit_cell",
            "absolute_mol_per_kg", "absolute_mg_per_g", "absolute_cm3_stp_per_g",
            "absolute_cm3_stp_per_cm3", "excess_molecules_per_unit_cell", "excess_mol_per_kg",
            "excess_mg_per_g", "excess_cm3_stp_per_g", "excess_cm3_stp_per_cm3", "qst_kj_mol",
            "warning_count", "source_file",
        ]
        output_rows = []
        for row in rows:
            index = int(row["array_index"])
            state = states.get(index, {"status": "missing", "warning_count": None})
            components = json.loads(row["components"])
            fractions = json.loads(row["fractions"])
            metric_names = [f"{kind}_{label}" for kind in ("absolute", "excess") for label in METRICS.values()]
            parsed = [{key: None for key in metric_names} | {"qst_kj_mol": None} for _ in components]
            source = state.get("output_file")
            if source and state["status"] in {"success", "completed_with_warnings"}:
                parsed = parse_gcmc(run_dir / source, len(components))
            for component_index, component in enumerate(components):
                output_rows.append({
                    "campaign": cfg["campaign"], "workflow": cfg["workflow"], "task_id": row["task_id"],
                    "status": state["status"], "framework": row["framework"], "temperature": row["temperature"],
                    "pressure": row["pressure"], "component_index": component_index, "component": component,
                    "mole_fraction": fractions[component_index], **parsed[component_index],
                    "warning_count": state.get("warning_count"), "source_file": source,
                })
        with (output_dir / "results_long.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(output_rows)
        return {"tasks": len(rows), "rows": len(output_rows)}

    trace_rows, optima_rows = [], []
    optima_dir = output_dir / "optima"
    optima_dir.mkdir(exist_ok=True)
    for row in rows:
        index = int(row["array_index"])
        state = states.get(index, {"status": "missing"})
        source = state.get("output_file")
        if not source or state["status"] not in {"success", "completed_with_warnings"}:
            optima_rows.append({"campaign": cfg["campaign"], "task_id": row["task_id"], "status": state["status"],
                                "framework": row["framework"], "component": json.loads(row["components"])[0],
                                "temperature": row["temperature"], "optimal_frame": "", "potential_energy": "",
                                "pdb_file": "", "source_file": source or ""})
            continue
        trace = extract_energy_trace(run_dir / source)
        for frame, energy in trace:
            trace_rows.append({"campaign": cfg["campaign"], "task_id": row["task_id"], "frame": frame,
                               "potential_energy": energy, "source_file": source})
        if not trace:
            optimal_frame, optimal_energy = "", ""
            pdb_rel = ""
        else:
            optimal_frame, optimal_energy = min(trace, key=lambda item: item[1])
            movies = sorted((run_dir / row["workdir"] / "Movies" / "System_0").glob("*_allcomponents.pdb"))
            destination = optima_dir / f"{row['task_id']}.pdb"
            pdb_rel = str(destination.relative_to(output_dir)) if len(movies) == 1 and extract_pdb_model(movies[0], optimal_frame, destination) else ""
        optima_rows.append({"campaign": cfg["campaign"], "task_id": row["task_id"], "status": state["status"],
                            "framework": row["framework"], "component": json.loads(row["components"])[0],
                            "temperature": row["temperature"], "optimal_frame": optimal_frame,
                            "potential_energy": optimal_energy, "pdb_file": pdb_rel, "source_file": source})
    for filename, data, fields in (
        ("energy_trace.csv", trace_rows, ["campaign", "task_id", "frame", "potential_energy", "source_file"]),
        ("optima.csv", optima_rows, ["campaign", "task_id", "status", "framework", "component", "temperature",
                                    "optimal_frame", "potential_energy", "pdb_file", "source_file"]),
    ):
        with (output_dir / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(data)
    return {"tasks": len(rows), "frames": len(trace_rows)}
