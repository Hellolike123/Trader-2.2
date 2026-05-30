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

# 确保 trader_shared 可被 import（其 __init__.py 会自动配置旧目录的 sys.path）
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

def _bootstrap_dependencies():
    """全自动自愈引导器：检测并静默安装缺失的三方库依赖"""
    required = []
    try:
        import akshare
    except ImportError:
        required.append("akshare")
    try:
        import mootdx
    except ImportError:
        required.append("mootdx")
        
    if required:
        import subprocess
        print(f"📡 [自愈引导器] 检测到服务器缺失基础行情库 {required}，正在为您全自动静默安装，请稍候...", file=sys.stderr)
        try:
            # 运行 pip 静默升级安装
            subprocess.run(
                [sys.executable, "-m", "pip", "install"] + required + ["--upgrade"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            print("✓ [自愈引导器] 依赖自动静默安装成功，系统已自愈！", file=sys.stderr)
        except Exception as e:
            print(f"⚠️ [自愈引导器] 自动静默安装失败: {e}，请手动执行 pip install {' '.join(required)}", file=sys.stderr)

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
    _bootstrap_dependencies()
    if len(sys.argv) < 2:
        print("Trader 2.4 大一统 CLI")
        print("用法: trader.py <command> [args...]")
        print("可用命令:")
        print("  analyze   - 单票分析")
        print("  monitor   - 盘中T0盯盘")
        print("  pool      - 选股池管理")
        print("  review    - 盘后复盘")
        print("  portfolio - 仓位轮动")
        print("  track     - 信号准确率追踪")
        print("  cache     - 缓存管理")
        sys.exit(1)

    command = sys.argv[1]
    
    # 截断 sys.argv，让底层的 argparse 正常工作
    # 比如 `trader.py pool add --target A` 会变成 `final_pool.py add --target A`
    sys.argv = [sys.argv[0]] + sys.argv[2:]

    if command == "analyze":
        sys.exit(_run_submodule("trader", "final_report"))
    elif command == "monitor":
        sys.exit(_run_submodule("t0", "final_t0"))
    elif command == "pool":
        sys.exit(_run_submodule("trader", "final_pool"))
    elif command == "review":
        sys.exit(_run_submodule("review", "final_review"))
    elif command == "portfolio":
        sys.exit(_run_submodule("review", "final_portfolio"))
    elif command == "track":
        sys.exit(_run_submodule("review", "final_tracker"))
    elif command == "cache":
        sys.exit(_handle_cache_command())
    else:
        print(f"未知命令: {command}")
        sys.exit(1)


def _handle_cache_command() -> int:
    """处理 trader.py cache 子命令。"""
    if len(sys.argv) < 2:
        print("用法: trader.py cache <subcommand>")
        print("可用子命令:")
        print("  clear [--type TYPE]  - 清空缓存")
        print("  warm                 - 预缓存选股池数据")
        return 1

    sub = sys.argv[1]
    if sub == "clear":
        from trader_shared.cache_utils import clear_cache
        cache_type = None
        if "--type" in sys.argv:
            idx = sys.argv.index("--type")
            if idx + 1 < len(sys.argv):
                cache_type = sys.argv[idx + 1]
        count = clear_cache(cache_type)
        label = cache_type or "all"
        print(f"已清空 {label} 缓存，删除 {count} 个文件")
        return 0
    elif sub == "warm":
        from trader_shared.cache_utils import warm_pool_cache
        result = warm_pool_cache()
        if result["success"] > 0:
            print(f"预缓存完成: {result['success']}/{result['total']} 成功")
        if result["failed"] > 0:
            print(f"预缓存失败: {result['failed']}/{result['total']}")
            for err in result.get("errors", []):
                print(f"  - {err}")
        return 0 if result["failed"] == 0 else 1
    else:
        print(f"未知缓存子命令: {sub}")
        return 1

if __name__ == "__main__":
    main()
