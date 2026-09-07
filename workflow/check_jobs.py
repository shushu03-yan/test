#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

from raspa_workflow.campaign import read_manifest


def _run(command: list[str]) -> str:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    return completed.stdout.strip() if completed.returncode == 0 else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="查看 campaign 的本地状态与 SLURM 状态")
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    run_dir = Path(args.run).resolve()
    rows = read_manifest(run_dir)
    counts = Counter()
    for row in rows:
        state_path = run_dir / "state" / f"{row['array_index']}.json"
        status = json.loads(state_path.read_text(encoding="utf-8")).get("status", "unknown") if state_path.exists() else "pending"
        counts[status] += 1
    print(f"任务总数: {len(rows)}")
    for status in sorted(counts):
        print(f"  {status}: {counts[status]}")
    history = run_dir / "submissions.jsonl"
    if not history.exists():
        print("尚未提交。")
        return 0
    job_ids = [json.loads(line)["job_id"] for line in history.read_text(encoding="utf-8").splitlines() if line.strip()]
    print("\nSLURM 当前队列:")
    print(_run(["squeue", "-j", ",".join(job_ids), "-o", "%.18i %.10T %.10M %R"]) or "  无在队作业")
    print("\nSLURM 历史状态:")
    print(_run(["sacct", "-j", ",".join(job_ids), "--format=JobID,State,Elapsed,ExitCode", "-P"]) or "  暂无记录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

