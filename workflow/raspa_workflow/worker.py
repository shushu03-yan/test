from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .campaign import read_manifest


def _write_state(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def run_task(run_dir: str | Path, index: int) -> dict:
    run_dir = Path(run_dir).resolve()
    rows = read_manifest(run_dir)
    matches = [row for row in rows if int(row["array_index"]) == index]
    if len(matches) != 1:
        raise RuntimeError(f"manifest 中数组索引 {index} 的记录数为 {len(matches)}")
    row = matches[0]
    task_dir = run_dir / row["workdir"]
    state_path = run_dir / "state" / f"{index}.json"
    attempt_id = os.environ.get("SLURM_JOB_ID") or datetime.now(timezone.utc).strftime("local-%Y%m%dT%H%M%S%f")
    generated = [task_dir / name for name in ("Output", "Movies", "Restart", "VTK", "Visualization")]
    if any(path.exists() for path in generated):
        history_dir = task_dir / "attempt_history" / f"{attempt_id}-preexisting"
        history_dir.mkdir(parents=True, exist_ok=False)
        for path in generated:
            if path.exists():
                shutil.move(str(path), history_dir / path.name)
    base = {
        "array_index": index,
        "task_id": row["task_id"],
        "attempt_id": attempt_id,
        "slurm_array_job_id": os.environ.get("SLURM_ARRAY_JOB_ID"),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
    }
    _write_state(state_path, {**base, "status": "running", "started_at": datetime.now(timezone.utc).isoformat()})
    stdout_path = run_dir / "logs" / f"{row['task_id']}.{attempt_id}.simulate.out"
    stderr_path = run_dir / "logs" / f"{row['task_id']}.{attempt_id}.simulate.err"
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        completed = subprocess.run(["simulate", "simulation.input"], cwd=task_dir, stdout=stdout, stderr=stderr,
                                   check=False)

    data_files = sorted((task_dir / "Output" / "System_0").glob("*.data"))
    text = data_files[0].read_text(encoding="utf-8", errors="replace") if len(data_files) == 1 else ""
    finished = "Finishing simulation" in text and "Simulation finished" in text
    warning_match = re.search(r"Simulation finished,\s*(\d+) warnings", text)
    warning_count = int(warning_match.group(1)) if warning_match else None
    if completed.returncode != 0 or len(data_files) != 1 or not finished:
        status = "failed"
    elif warning_count == 0:
        status = "success"
    else:
        status = "completed_with_warnings"
    payload = {
        **base,
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "exit_code": completed.returncode,
        "output_file": str(data_files[0].relative_to(run_dir)) if len(data_files) == 1 else None,
        "output_file_count": len(data_files),
        "completion_markers": finished,
        "warning_count": warning_count,
    }
    _write_state(state_path, payload)
    history_state = run_dir / "state" / f"{index}.{attempt_id}.json"
    _write_state(history_state, payload)
    return payload
