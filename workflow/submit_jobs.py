#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from raspa_workflow.campaign import read_manifest


def index_spec(indices: list[int]) -> str:
    if not indices:
        return ""
    ranges = []
    start = previous = indices[0]
    for value in indices[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = value
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ",".join(ranges)


def main() -> int:
    parser = argparse.ArgumentParser(description="提交 RASPA SLURM Job Array")
    parser.add_argument("--run", required=True)
    parser.add_argument("--resume", action="store_true", help="仅提交缺失、失败或中断的任务")
    parser.add_argument("--dry-run", action="store_true", help="只打印 sbatch 命令")
    args = parser.parse_args()
    run_dir = Path(args.run).resolve()
    rows = read_manifest(run_dir)
    cfg = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    history = run_dir / "submissions.jsonl"
    if history.exists() and not args.resume:
        print("该 campaign 已有提交记录；如需续跑请使用 --resume", file=sys.stderr)
        return 2

    selected = []
    for row in rows:
        index = int(row["array_index"])
        state_path = run_dir / "state" / f"{index}.json"
        status = json.loads(state_path.read_text(encoding="utf-8")).get("status") if state_path.exists() else "missing"
        if not args.resume or status in {"missing", "failed"}:
            selected.append(index)
    if not selected:
        print("没有需要提交的任务。")
        return 0

    array_spec = f"{index_spec(selected)}%{cfg['resources']['max_concurrent']}"
    command = ["sbatch", "--parsable", f"--array={array_spec}", str(run_dir / "array_job.sh")]
    print(" ".join(command))
    if args.dry_run:
        return 0
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode:
        print(completed.stderr.strip(), file=sys.stderr)
        return completed.returncode
    job_id = completed.stdout.strip().split(";", 1)[0]
    record = {"job_id": job_id, "submitted_at": datetime.now(timezone.utc).isoformat(),
              "indices": selected, "resume": args.resume}
    with history.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    print(f"已提交 Job Array: {job_id} ({len(selected)} 项)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
