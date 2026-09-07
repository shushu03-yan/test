#!/usr/bin/env python3
import argparse
import sys

from raspa_workflow.worker import run_task


def main() -> int:
    parser = argparse.ArgumentParser(description="运行一个 SLURM array 元素")
    parser.add_argument("--run", required=True)
    parser.add_argument("--index", required=True, type=int)
    args = parser.parse_args()
    try:
        state = run_task(args.run, args.index)
    except Exception as exc:
        print(f"数组任务启动失败: {exc}", file=sys.stderr)
        return 2
    print(f"{state['task_id']}: {state['status']} (exit={state['exit_code']}, warnings={state['warning_count']})")
    return 0 if state["status"] in {"success", "completed_with_warnings"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

