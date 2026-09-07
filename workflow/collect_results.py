#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from raspa_workflow.results import collect


def main() -> int:
    parser = argparse.ArgumentParser(description="按 manifest 汇总 RASPA campaign 结果")
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    run_dir = Path(args.run).resolve()
    try:
        cfg = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
        root = run_dir.parents[2]
        summary = collect(run_dir, root / "results")
    except Exception as exc:
        print(f"汇总失败: {exc}", file=sys.stderr)
        return 2
    print(f"结果已写入 {root / 'results' / cfg['workflow'] / cfg['campaign']}: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

