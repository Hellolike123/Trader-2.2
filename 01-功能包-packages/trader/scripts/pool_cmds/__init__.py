"""选股池命令实现：逻辑在 service，CLI 在 cli，薄门面在各 cmd 模块。"""
# 避免 import pool_cmds 时立刻拉起重依赖；由 final_pool / cli 显式 import main。
__all__ = ["main"]


def __getattr__(name: str):
    if name == "main":
        from pool_cmds.cli import main as _main

        return _main
    raise AttributeError(name)
