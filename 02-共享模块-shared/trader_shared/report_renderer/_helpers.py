"""report_renderer helpers — 单一实现（不再 re-export report_core）。"""
from __future__ import annotations

import os
import re
import warnings


def _short_midline_enabled() -> bool:
    """生产始终短中线；SHORT_MIDLINE_REPORT=false 仅告警后仍返回 True。"""
    env = os.environ.get("SHORT_MIDLINE_REPORT")
    if env is not None and env.lower() not in ("true", "1", "yes"):
        warnings.warn(
            "SHORT_MIDLINE_REPORT=false is deprecated and ignored; "
            "production render is always report_renderer.short_midline.",
            DeprecationWarning,
            stacklevel=3,
        )
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
    # 压力/目标（旧合并文案）→ 统一压力位，去掉止盈暗示
    m = re.match(r"^压力/目标\s+([\d.]+)（(.+)）$", line)
    if m:
        _tag = m.group(2).replace("靠近只减不加", "靠近分批减仓").replace("波段上看", "结构参考").replace("到了分批止盈", "结构参考")
        return f"{m.group(1)} 压力位（{_tag}）"
    # 压力
    m = re.match(r"^压力\s+([\d.]+)（(.+)）$", line)
    if m:
        _tag = m.group(2).replace("靠近只减不加", "靠近分批减仓")
        return f"{m.group(1)} 压力位（{_tag}）"
    # 目标/远档结构（不做止盈指令）
    m = re.match(r"^(?:目标|远档结构)\s+([\d.]+)（(.+)）$", line)
    if m:
        return f"{m.group(1)} 远档结构（仅对照）"
    # 黄金买点
    m = re.match(r"^黄金买点\s+([\d.]+)（(.+)）$", line)
    if m:
        return f"{m.group(1)} 黄金买点（{m.group(2)}）"
    return line


def _is_closed_stance(
    *,
    allow_new_entry: bool = True,
    execution: str = "",
) -> bool:
    """关闭态：纪律否决新开，或动作文案含不新开/不买/不追/观望。"""
    if not allow_new_entry:
        return True
    exe = str(execution or "")
    return any(k in exe for k in ("不新开", "不买", "不追", "观望"))


def _soften_mid_key_entry_verbs(line: str) -> str:
    """D-R6：关闭态/偏空时中线关键价去掉低吸出手动词（仅展示词）。"""
    if not line or "低吸" not in line:
        return line
    out = line
    if "回踩区" in out:
        def _pb(m: re.Match[str]) -> str:
            inner = m.group(1)
            parts = [p.strip() for p in inner.split("·") if p.strip()]
            parts = [p for p in parts if "低吸" not in p]
            if not parts:
                parts = ["结构参考"]
            elif "结构参考" not in "".join(parts):
                parts.append("结构参考")
            return "（" + " · ".join(parts) + "）"

        out = re.sub(r"（([^）]*)）", _pb, out, count=1)
    if "黄金买点" in out or "黄金位" in out:
        out = out.replace("黄金买点", "黄金位")
        out = out.replace("最佳低吸位", "")
        # 若仍残留其它「低吸」字样，整段注解降为 50%回撤 / 结构参考
        if "低吸" in out:
            def _gold(m: re.Match[str]) -> str:
                inner = m.group(1)
                parts = [p.strip() for p in inner.split("·") if p.strip() and "低吸" not in p]
                if not parts:
                    parts = ["50%回撤"]
                elif not any("回撤" in p or "结构参考" in p for p in parts):
                    parts.append("50%回撤")
                return "（" + " · ".join(parts) + "）"

            out = re.sub(r"（([^）]*)）", _gold, out, count=1)
        out = re.sub(r"·\s*·", "·", out)
        out = re.sub(r"（\s*·\s*", "（", out)
        out = re.sub(r"\s*·\s*）", "）", out)
        out = re.sub(r"（\s*）", "（50%回撤）", out)
    return out


def _rewrite_declutter_verdict_note(
    note: str,
    *,
    bias_tag: str,
    bias_short: str,
    mid: str,
    weekly_frame: str | None,
    stage_line: str = "",
) -> str | None:
    """D-R1：偏空/框破坏 +「双源无明确方向」→ 单一连贯定论句；否则 None。"""
    note = str(note or "").strip()
    if "双源无明确方向" not in note:
        return None
    mid_s = str(mid or "")
    frame_break = (
        str(weekly_frame or "") == "破坏"
        or "框破坏" in mid_s
        or "战略减" in mid_s
    )
    if bias_tag != "偏空" and not frame_break:
        return None
    m = re.search(r"威科夫(.+?)\s*×\s*缠论(.+?)\s*→", note)
    wyck = (m.group(1).strip() if m else "") or (str(stage_line or "").strip() or "无阶段")
    chan = (m.group(2).strip() if m else "") or "盘整"
    # 副读词过长时截到首段
    chan = re.split(r"[（(]", chan, maxsplit=1)[0].strip() or chan
    if frame_break:
        return f"中线框破坏 · 偏空 · 战略减（周线威科夫{wyck}，缠论{chan}仅副读）"
    bias_part = f"偏空（{bias_short}）" if bias_short else "偏空"
    return f"{bias_part}（周线威科夫{wyck}，缠论{chan}仅副读）"
