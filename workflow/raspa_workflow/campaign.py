from __future__ import annotations

import csv
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Iterable

from .cif import compute_supercell, read_cell
from .config import FORCEFIELD_FILES, ConfigError, load_and_validate
from .render import render_simulation

MANIFEST_FIELDS = (
    "array_index", "task_id", "workflow", "framework", "temperature", "pressure",
    "components", "fractions", "unitcells", "workdir",
)


def slug(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-.")
    return text or "item"


def _tasks(cfg: dict[str, Any], structures: Iterable[Path]) -> list[dict[str, Any]]:
    sim = cfg["simulation"]
    workflow = cfg["workflow"]
    combinations: list[tuple[str, list[str], list[float]]] = []
    if workflow in {"single", "minimization"}:
        combinations = [(name, [name], [1.0]) for name in cfg["adsorbates"]]
    else:
        combinations = [
            (mixture["name"], list(mixture["components"]), list(mixture["fractions"]))
            for mixture in cfg["mixtures"]
        ]
    pressures = sim.get("pressures", [None]) if workflow != "minimization" else [None]
    result: list[dict[str, Any]] = []
    for cif in sorted(structures, key=lambda p: p.name.lower()):
        framework = cif.stem
        if framework in cfg.get("supercells", {}):
            unitcells = tuple(cfg["supercells"][framework])
        else:
            unitcells = compute_supercell(read_cell(cif), float(sim.get("supercell_min_length", 2 * sim["cutoff"])))
        for label, components, fractions in combinations:
            for temperature in sim["temperatures"]:
                for pressure in pressures:
                    parts = [framework, label, f"T{temperature:g}"]
                    if pressure is not None:
                        parts.append(f"P{pressure:g}")
                    result.append({
                        "framework": framework,
                        "cif": cif,
                        "temperature": temperature,
                        "pressure": pressure,
                        "components": components,
                        "fractions": fractions,
                        "unitcells": unitcells,
                        "label": slug("__".join(parts)),
                    })
    return result


def _relative_symlink(source: Path, target: Path) -> None:
    target.symlink_to(os.path.relpath(source, target.parent))


def _write_array_script(run_dir: Path, project_root: Path, cfg: dict[str, Any]) -> None:
    resources = cfg["resources"]
    script = f"""#!/bin/bash
#SBATCH --job-name=raspa_{slug(cfg['campaign'])}
#SBATCH --partition={resources['partition']}
#SBATCH --qos={resources['qos']}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={resources['cpus_per_task']}
#SBATCH --mem={resources['memory']}
#SBATCH --time={resources['time']}
#SBATCH --output={run_dir}/logs/slurm_%A_%a.out
#SBATCH --error={run_dir}/logs/slurm_%A_%a.err

set -uo pipefail
module load raspa2
python3 {project_root / 'run_array_task.py'} --run {run_dir} --index "${{SLURM_ARRAY_TASK_ID:?}}"
"""
    path = run_dir / "array_job.sh"
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def prepare_campaign(config_path: str | Path) -> Path:
    cfg, root = load_and_validate(config_path)
    run_dir = root / "runs" / cfg["workflow"] / cfg["campaign"]
    if run_dir.exists():
        raise ConfigError(f"campaign 已存在，拒绝覆盖: {run_dir}")

    paths = cfg["paths"]
    source_structures = (root / paths["structures"]).resolve()
    source_forcefield = (root / paths["forcefield"]).resolve()
    source_molecules = (root / paths["molecules"]).resolve()
    structures = sorted(source_structures.glob("*.cif"))
    tasks = _tasks(cfg, structures)

    for directory in ("assets/forcefield", "assets/molecules", "assets/structures",
                      "assets/frameworks", "tasks", "logs", "state"):
        (run_dir / directory).mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for name in FORCEFIELD_FILES:
        shutil.copy2(source_forcefield / name, run_dir / "assets/forcefield" / name)
    used_molecules = sorted({component for task in tasks for component in task["components"]})
    for name in used_molecules:
        shutil.copy2(source_molecules / f"{name}.def", run_dir / "assets/molecules" / f"{name}.def")
    for cif in structures:
        shutil.copy2(cif, run_dir / "assets/structures" / cif.name)

    flexible = cfg.get("flexible", {})
    if flexible.get("enabled"):
        for framework, relpath in flexible["framework_definitions"].items():
            destination = run_dir / "assets/frameworks" / framework
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2((root / relpath).resolve(), destination / "framework.def")

    manifest_rows = []
    for index, task in enumerate(tasks):
        task_id = f"{index:05d}__{task['label']}"
        task_dir = run_dir / "tasks" / task_id
        task_dir.mkdir()
        task["task_id"] = task_id
        task["array_index"] = index
        (task_dir / "simulation.input").write_text(render_simulation(cfg, task), encoding="utf-8")
        _relative_symlink(run_dir / "assets/structures" / task["cif"].name, task_dir / task["cif"].name)
        for filename in FORCEFIELD_FILES:
            _relative_symlink(run_dir / "assets/forcefield" / filename, task_dir / filename)
        for component in task["components"]:
            _relative_symlink(run_dir / "assets/molecules" / f"{component}.def", task_dir / f"{component}.def")
        if flexible.get("enabled"):
            _relative_symlink(run_dir / "assets/frameworks" / task["framework"] / "framework.def",
                              task_dir / "framework.def")
        manifest_rows.append({
            "array_index": index,
            "task_id": task_id,
            "workflow": cfg["workflow"],
            "framework": task["framework"],
            "temperature": task["temperature"],
            "pressure": "" if task["pressure"] is None else task["pressure"],
            "components": json.dumps(task["components"], separators=(",", ":")),
            "fractions": json.dumps(task["fractions"], separators=(",", ":")),
            "unitcells": json.dumps(task["unitcells"], separators=(",", ":")),
            "workdir": str(Path("tasks") / task_id),
        })

    with (run_dir / "manifest.tsv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest_rows)
    _write_array_script(run_dir, root, cfg)
    return run_dir


def read_manifest(run_dir: str | Path) -> list[dict[str, str]]:
    with (Path(run_dir).resolve() / "manifest.tsv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))

