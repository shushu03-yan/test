#!/usr/bin/env python3
import argparse
import sys

from raspa_workflow.campaign import prepare_campaign, read_manifest
from raspa_workflow.config import ConfigError


def main() -> int:
    parser = argparse.ArgumentParser(description="生成不可覆盖的 RASPA campaign 和 Job Array manifest")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        run_dir = prepare_campaign(args.config)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"生成失败: {exc}", file=sys.stderr)
        return 2
    print(f"已生成 {len(read_manifest(run_dir))} 个任务: {run_dir}")
    print(f"提交命令: python3 submit_jobs.py --run {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

