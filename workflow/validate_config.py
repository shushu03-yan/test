#!/usr/bin/env python3
import argparse
import sys

from raspa_workflow.config import ConfigError, load_and_validate


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 RASPA campaign 配置及引用资源")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        cfg, root = load_and_validate(args.config)
    except ConfigError as exc:
        print(f"配置无效: {exc}", file=sys.stderr)
        return 2
    print(f"配置有效: workflow={cfg['workflow']} campaign={cfg['campaign']} root={root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

