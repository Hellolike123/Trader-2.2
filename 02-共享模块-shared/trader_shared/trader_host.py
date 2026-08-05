"""运行宿主识别：Hermes（Tushare）vs WorkBuddy（Tdx 优先）。

Skill 仍只跑脚本；取数源在此分流，Agent 不插手 MCP。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

HOST_HERMES = "hermes"
HOST_WORKBUDDY = "workbuddy"
HOST_LOCAL = "local"
_VALID = frozenset({HOST_HERMES, HOST_WORKBUDDY, HOST_LOCAL})


def workbuddy_connectors_dir() -> Path:
    return Path(os.path.expanduser("~/.workbuddy/connectors"))


def workbuddy_connectors_present() -> bool:
    d = workbuddy_connectors_dir()
    if not d.is_dir():
        return False
    try:
        for child in d.iterdir():
            if (child / "connector-states.v3.json").is_file():
                return True
    except OSError:
        return False
    return False


def _host_from_skill_config() -> str:
    """打包后 config.json 可能含 trader_host（与 tushare_token 同文件）。"""
    # 包内: skill/scripts/trader_shared/trader_host.py → skill/
    # 仓内: 02-共享模块-shared/trader_shared/ → 仓库根（通常无 config.json）
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "config.json",  # …/scripts/trader_shared → skill 根
        here.parents[3] / "config.json",  # 兜底
    ]
    for cfg_path in candidates:
        if not cfg_path.is_file():
            continue
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        h = str(cfg.get("trader_host") or "").strip().lower()
        if h in _VALID:
            return h
    return ""


def detect_trader_host() -> str:
    """返回 hermes | workbuddy | local。

    优先级：TRADER_HOST env → skill config.json → 探测 ~/.workbuddy/connectors → hermes。
    """
    env = os.environ.get("TRADER_HOST", "").strip().lower()
    if env in _VALID:
        return env
    from_cfg = _host_from_skill_config()
    if from_cfg:
        return from_cfg
    if workbuddy_connectors_present():
        return HOST_WORKBUDDY
    return HOST_HERMES


def fund_flow_source_order() -> list[str]:
    """资金流瀑布顺序。WorkBuddy：tdx 优先；其余：tushare 优先。

    免费 HTTP 备源只用新浪（sina）；不再走东财/akshare。
    """
    if detect_trader_host() == HOST_WORKBUDDY:
        return ["tdx", "tushare", "sina"]
    return ["tushare", "tdx", "sina"]
