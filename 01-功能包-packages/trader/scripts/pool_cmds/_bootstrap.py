"""Path / import bootstrap for pool_cmds (Hermes pack + repo layout)."""
from __future__ import annotations

import sys
from pathlib import Path


def ensure_imports() -> None:
    try:
        import trader_shared  # noqa: F401
    except ImportError:
        _d = Path(__file__).resolve().parent
        for _ in range(10):
            if (_d / "trader_shared").is_dir():
                if str(_d) not in sys.path:
                    sys.path.insert(0, str(_d))
                break
            shared = _d / "02-共享模块-shared"
            if (shared / "trader_shared").is_dir():
                if str(shared) not in sys.path:
                    sys.path.insert(0, str(shared))
                break
            _d = _d.parent
        else:
            raise ImportError("trader_shared not found")
        import trader_shared  # noqa: F401

    # trader/scripts 必须优先于 shared：本地 config.py 与 trader_shared.config 同名
    scripts = Path(__file__).resolve().parents[1]
    scripts_s = str(scripts)
    if scripts_s in sys.path:
        sys.path.remove(scripts_s)
    sys.path.insert(0, scripts_s)
    # 若已误载 shared 的 config，清掉以便重载技能包配置
    mod = sys.modules.get("config")
    if mod is not None and getattr(mod, "__file__", "") and "trader_shared" in str(mod.__file__):
        del sys.modules["config"]
