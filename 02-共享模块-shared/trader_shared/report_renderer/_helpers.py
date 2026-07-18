"""report_renderer helpers — 单一实现（不再 re-export report_core）。"""
from __future__ import annotations

import os
import re

def _short_midline_enabled() -> bool:
    # 优先读 env，其次 config 常量
    env = os.environ.get("SHORT_MIDLINE_REPORT")
    if env is not None:
        return env.lower() in ("true", "1", "yes")
    try:
        from trader_shared.config import SHORT_MIDLINE_REPORT
        return bool(SHORT_MIDLINE_REPORT)
    except Exception:
        return True


def _reformat_mid_line(line: str) -> str:
    """中线关键价行格式转换：价格前置 + 动作统一。

    旧格式「生命线 41.14（破则中线转弱）」→ 新格式「41.14 生命线（跌破则减仓）」。
    已是新格式时原样返回。
    """
    if not line:
        return line
    # 生命线
    m = re.match(r"^生命线\s+([\d.]+)（.+）$", line)
    if m:
        return f"{m.group(1)} 生命线（跌破则减仓）"
    # 回踩区（含区间或单价）
    m = re.match(r"^回踩区\s+([\d.-]+)（(.+)）$", line)
    if m:
        _tag = m.group(2).replace("到了才谈低吸", "到了分批低吸")
        return f"{m.group(1)} 回踩区（{_tag}）"
    # 压力/目标（合并）
    m = re.match(r"^压力/目标\s+([\d.]+)（(.+)）$", line)
    if m:
        _tag = m.group(2).replace("靠近只减不加", "靠近分批减仓").replace("波段上看", "到了分批止盈")
        return f"{m.group(1)} 压力/目标位（{_tag}）"
    # 压力
    m = re.match(r"^压力\s+([\d.]+)（(.+)）$", line)
    if m:
        _tag = m.group(2).replace("靠近只减不加", "靠近分批减仓")
        return f"{m.group(1)} 压力位（{_tag}）"
    # 目标
    m = re.match(r"^目标\s+([\d.]+)（(.+)）$", line)
    if m:
        return f"{m.group(1)} 目标位（到了分批止盈）"
    # 黄金买点
    m = re.match(r"^黄金买点\s+([\d.]+)（(.+)）$", line)
    if m:
        return f"{m.group(1)} 黄金买点（{m.group(2)}）"
    return line


