#!/usr/bin/env python3
"""快速创建带模板的变更提案。

用法:
    python scripts/quick_change.py --type performance --name "fix-atr-merge"
    python scripts/quick_change.py --type data-fix --name "fix-fund-flow-encoding"
    python scripts/quick_change.py --type feature --name "add-main-force"
    python scripts/quick_change.py --type display --name "add-chip-section"
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "openspec" / "templates"
CHANGES_DIR = Path(__file__).resolve().parent.parent / "openspec" / "changes"

TEMPLATE_MAP = {
    "performance": "performance.md",
    "data-fix": "data-fix.md",
    "feature": "feature.md",
    "display": "display.md",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="快速创建变更提案")
    parser.add_argument("--type", required=True, choices=list(TEMPLATE_MAP.keys()),
                        help="变更类型：performance/data-fix/feature/display")
    parser.add_argument("--name", required=True, help="变更名称（kebab-case）")
    parser.add_argument("--open", action="store_true", help="创建后在编辑器中打开")
    args = parser.parse_args()

    template_file = TEMPLATES_DIR / TEMPLATE_MAP[args.type]
    if not template_file.exists():
        print(f"模板文件不存在：{template_file}")
        return 1

    change_dir = CHANGES_DIR / args.name
    if change_dir.exists():
        print(f"变更目录已存在：{change_dir}")
        return 1

    change_dir.mkdir(parents=True)
    proposal = change_dir / "proposal.md"
    shutil.copy2(template_file, proposal)

    # 创建 tasks.md 骨架
    tasks = change_dir / "tasks.md"
    tasks.write_text(f"## 1. 实施\n\n- [ ] 1.1 [待填写]\n", encoding="utf-8")

    print(f"已创建变更提案：{change_dir}")
    print(f"  proposal.md — 从 {args.type} 模板生成")
    print(f"  tasks.md — 任务骨架")
    print(f"\n下一步：编辑 {proposal} 填写具体内容")

    if args.open:
        import subprocess
        editor = "code"  # VS Code
        try:
            subprocess.run([editor, str(proposal)], check=False)
        except FileNotFoundError:
            print(f"编辑器 {editor} 未找到，请手动打开 {proposal}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
