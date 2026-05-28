#!/usr/bin/env python3
import sys
import os
import json
import subprocess
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def get_active_pool_stocks() -> list[str]:
    """读取选股池，获取所有未被淘汰且未退出的活跃股票"""
    pool_path = Path.home() / ".trader" / "pool.json"
    if not pool_path.exists():
        return []
    try:
        with open(pool_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("items", [])
        active_stocks = [
            item["name"] for item in items 
            if item.get("status") not in {"淘汰", "已退出"}
        ]
        return active_stocks
    except Exception as e:
        print(f"读取选股池失败: {e}", file=sys.stderr)
        return []

def main():
    parser = argparse.ArgumentParser(description="Hermes T0 WeChat Monitor")
    parser.add_argument("--targets", nargs="*", help="手动指定监控股票列表，若不指定则自动读取选股池")
    parser.add_argument("--verbose", action="store_true", help="打印详细调试信息")
    args = parser.parse_args()

    # 1. 确定需要监控的目标
    if args.targets:
        targets = args.targets
        if args.verbose:
            print(f"使用手动指定的股票列表: {targets}")
    else:
        targets = get_active_pool_stocks()
        if args.verbose:
            print(f"从选股池读取到活跃股票: {targets}")

    if not targets:
        if args.verbose:
            print("没有找到需要监控的股票目标。")
        return 0

    results = []
    
    # 2. 逐一扫描股票
    for stock in targets:
        if args.verbose:
            print(f"正在扫描: {stock} ...")
        
        # 运行 trader.py 进行 T0 监控单次检查
        cmd = [sys.executable, str(ROOT / "trader.py"), "monitor", "--target", stock, "--monitor", "--once"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), encoding="utf-8")
            output = res.stdout.strip()
            
            # 如果输出中包含有效的警报信息（排除空输出或"无新提醒"）
            if output and "无新提醒" not in output:
                results.append(output)
        except Exception as e:
            if args.verbose:
                print(f"扫描 {stock} 失败: {e}", file=sys.stderr)

    # 3. 输出汇总结果 (如果没有信号则完全静默，不打印任何东西)
    if results:
        # 使用符合微信卡片排版的双线横栏分隔多个股票，避免使用禁用的 --- / ***
        divider = "\n\n════════════════════\n\n"
        combined_output = divider.join(results)
        print(combined_output)
    else:
        if args.verbose:
            print("所有股票均无新交易信号，静默退出。")

if __name__ == "__main__":
    sys.exit(main())
