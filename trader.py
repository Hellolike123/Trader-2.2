#!/usr/bin/env python3
"""
Trader 2.3 统一大总管 (Facade Router)
负责集中处理 sys.path 配置，并将执行请求透明分发到原有的 6 个独立模块。
"""
import sys
import os
from pathlib import Path

# 配置全局环境
ROOT = Path(__file__).resolve().parent
PACKAGES_DIR = ROOT / "01-功能包-packages"
SHARED_DIR = ROOT / "02-共享模块-shared"

# 统一注入底层模型路径，彻底解决原脚本里的意大利面条代码
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))
for _sub in ["01-行情数据-market-data", "02-候选逻辑-candidate", "03-输出校验-contracts"]:
    _p = SHARED_DIR / _sub
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

def _run_submodule(module_dir: str, script_name: str) -> int:
    """动态加载子模块并调用其 main 函数"""
    target_path = PACKAGES_DIR / module_dir / "scripts"
    if str(target_path) not in sys.path:
        sys.path.insert(0, str(target_path))
    
    import importlib
    module_name = script_name.replace(".py", "")
    try:
        mod = importlib.import_module(module_name)
    except ImportError as e:
        print(f"Failed to load module {module_name} in {module_dir}: {e}", file=sys.stderr)
        return 1
        
    if hasattr(mod, "main"):
        return mod.main()
    else:
        print(f"Module {module_name} does not expose main().", file=sys.stderr)
        return 1

def main():
    if len(sys.argv) < 2:
        print("Trader 2.3 大一统 CLI")
        print("用法: trader.py <command> [args...]")
        print("可用命令:")
        print("  analyze   - 单票分析")
        print("  monitor   - 盘中T0盯盘")
        print("  pool      - 选股池管理")
        print("  review    - 盘后复盘")
        print("  portfolio - 仓位轮动")
        print("  track     - 信号准确率追踪")
        sys.exit(1)

    command = sys.argv[1]
    
    # 截断 sys.argv，让底层的 argparse 正常工作
    # 比如 `trader.py pool add --target A` 会变成 `final_pool.py add --target A`
    sys.argv = [sys.argv[0]] + sys.argv[2:]

    if command == "analyze":
        sys.exit(_run_submodule("01-单票分析-trader", "final_report"))
    elif command == "monitor":
        sys.exit(_run_submodule("02-盘中T0-t0-trader", "final_t0"))
    elif command == "pool":
        sys.exit(_run_submodule("03-选股池-trader-pool", "final_pool"))
    elif command == "review":
        sys.exit(_run_submodule("05-盘后复盘-review-trader", "final_review"))
    elif command == "portfolio":
        sys.exit(_run_submodule("04-仓位轮动-trader-portfolio", "final_portfolio"))
    elif command == "track":
        sys.exit(_run_submodule("06-信号追踪-trader-tracking", "final_tracker"))
    else:
        print(f"未知命令: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
