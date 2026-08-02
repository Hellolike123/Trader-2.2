"""短中线结论块：中线看法（周线理论）/ 短线看法 / 出手 / 原因 / 本周 / 冲突说明。

规格：docs/mid-short-dual-track-plan.md（B3C / B1A）。
"""
from __future__ import annotations

import re
from typing import Any

from trader_shared.mistery_gate import gate_action_to_execution_text

# 看法行禁止四阶段词（B3C）
_STAGE_WORDS_RE = re.compile(r"蓄势|主升|派发|衰退")

# 笔尖离价兜底：现价相对末笔终点反向偏离超过该比例 → 禁止「拉升趋势中」假有
# （华工对照：末笔延伸至高点后砸跌近半，反向笔尚未确认时浪型不得继续喊拉升）
_STROKE_TIP_LEAVE_PCT = 0.15


def _stroke_tip_left_against(strokes: list, current: float, leave_pct: float = _STROKE_TIP_LEAVE_PCT) -> str:
    """现价是否已反向大幅离开末笔终点（反向笔尚未确认时的展示闸）。

    返回：
      "" — 未离开或无法判断
      "up_left" — 末笔向上，现价明显低于笔终点（高点已离开）
      "down_left" — 末笔向下，现价明显高于笔终点（低点已离开）
    """
    if not strokes or not current or current <= 0:
        return ""
    last = strokes[-1] if isinstance(strokes[-1], dict) else None
    if not last:
        return ""
    try:
        ep = float(last.get("end_price") or 0)
    except (TypeError, ValueError):
        return ""
    if ep <= 0:
        return ""
    direction = str(last.get("direction") or "")
    gap = (current - ep) / ep
    if direction == "up" and gap <= -leave_pct:
        return "up_left"
    if direction == "down" and gap >= leave_pct:
        return "down_left"
    return ""


def _build_wave_label(chanlun_daily: Any, current: float = 0.0) -> str:
    """从日线缠论数据推导浪型叙事，用于波段交易提示。

    将缠论的「段」翻译为波段交易员熟悉的浪型语言。
    不是严格的 Elliott 波浪计数，而是基于缠论结构的浪型叙事。
    """
    chan = _unwrap_chan(chanlun_daily)
    if not chan:
        return ""

    segments = chan.get("segments") if isinstance(chan.get("segments"), list) else []
    strokes = chan.get("strokes") if isinstance(chan.get("strokes"), list) else []
    trend_label = str(chan.get("trend_label") or "")
    structure_type = str(chan.get("structure_type") or "")
    buy_points = chan.get("buy_points") if isinstance(chan.get("buy_points"), list) else []
    sell_points = chan.get("sell_points") if isinstance(chan.get("sell_points"), list) else []
    divergence = chan.get("divergence") if isinstance(chan.get("divergence"), dict) else {}
    merged_zones = chan.get("merged_zones") if isinstance(chan.get("merged_zones"), list) else []
    tip_left = _stroke_tip_left_against(strokes, float(current or 0))

    # ── 段数不足（<2）：优先用 trend_label / structure / 笔级叙事 ──
    # 禁止「笔数不足」误报（有笔无线段）；禁止「线段不足/无法判断」——段少也要给可执行立场。
    if len(segments) < 2:
        has_sell = any(
            isinstance(p, dict) and p.get("type") and "卖" in str(p.get("type", ""))
            for p in sell_points
        ) or divergence.get("top_divergence", False)
        has_buy = any(
            isinstance(p, dict) and p.get("type") and "买" in str(p.get("type", ""))
            for p in buy_points
        ) or divergence.get("bottom_divergence", False)
        _sig = _signal_overlay(buy_points, sell_points, divergence)

        def _thin_struct_label() -> str:
            # 笔尖已反向离开：禁止再用拉升/回调「趋势中」假叙事（C-D4 展示兜底）
            if tip_left == "up_left":
                return "高点已离开·向下未成笔"
            if tip_left == "down_left":
                return "低点已离开·向上未成笔"
            if trend_label == "拉升段":
                return "拉升遇阻" if has_sell else "拉升趋势中"
            if trend_label == "回调段":
                return "回调见底" if has_buy else "回调一笔中"
            if trend_label == "震荡段":
                return "震荡中"
            if structure_type and structure_type not in ("", "无结构") and not structure_type.startswith("线段不足"):
                return structure_type
            # 真没结构：立场仍是「先观望」，不是「无法判断」
            return "中枢未成型"

        if len(strokes) < 3:
            return "笔数不足 · 先观望"

        _base = _thin_struct_label()
        if _sig:
            return f"{_base} · {_sig}"
        if _base == "中枢未成型":
            return "中枢未成型 · 先观望"
        _seg_note = "线段偏少" if len(segments) == 1 else "线段未成型"
        return f"{_base} · {_seg_note}"

    # ── 段数足够：用缠论走势分类 ──
    recent_segs = segments[-8:] if len(segments) >= 8 else segments
    directions = [s.get("direction", "") for s in recent_segs if isinstance(s, dict)]

    if not directions:
        return "无明确结构"

    def _count_consecutive(dirs: list[str], target: str) -> int:
        count = 0
        for d in reversed(dirs):
            if d == target:
                count += 1
            else:
                break
        return count

    up_count = _count_consecutive(directions, "up")
    down_count = _count_consecutive(directions, "down")

    last_zone = None
    for z in reversed(merged_zones):
        if isinstance(z, dict) and z.get("valid", True):
            last_zone = z
            break

    # ── 缠论走势分类输出 ──
    parts: list[str] = []

    if tip_left == "up_left":
        parts.append("高点已离开·向下未成笔")
    elif tip_left == "down_left":
        parts.append("低点已离开·向上未成笔")
    elif trend_label == "拉升段":
        if up_count >= 3:
            parts.append("趋势延续 · 笔力递增")
        elif up_count >= 1 and down_count >= 1:
            parts.append("趋势回调确认中")
        else:
            parts.append("拉升趋势中")

    elif trend_label == "回调段":
        if down_count >= 2:
            parts.append("回调确认中 · 关注一笔底")
        elif down_count >= 1 and up_count >= 1:
            parts.append("回调一笔中")
        else:
            parts.append("回调趋势")

    elif trend_label == "震荡段":
        if last_zone:
            zt = last_zone.get("zh_top", 0)
            zb = last_zone.get("zh_bottom", 0)
            if current > 0 and zt > 0 and zb > 0:
                pos = (current - zb) / (zt - zb) if zt > zb else 0.5
                if pos > 0.7:
                    parts.append("中枢震荡 · 靠近上沿")
                elif pos < 0.3:
                    parts.append("中枢震荡 · 靠近下沿")
                else:
                    parts.append("中枢震荡")
            else:
                parts.append("中枢震荡")
        else:
            parts.append("盘整震荡")

    elif "单边上涨" in structure_type:
        parts.append("单边上涨")
    elif "单边下跌" in structure_type:
        parts.append("单边下跌")
    elif structure_type == "无结构":
        parts.append("无明确结构")
    else:
        if up_count > down_count:
            parts.append("偏多震荡")
        elif down_count > up_count:
            parts.append("偏空震荡")
        else:
            parts.append("多空平衡")

    _sig = _signal_overlay(buy_points, sell_points, divergence)
    result = parts[0] if parts else ""
    if _sig:
        result += f" · {_sig}"

    return result


def _signal_overlay(
    buy_points: list, sell_points: list, divergence: dict
) -> str:
    """从买卖点和背驰生成信号叠加文本。

    有卖点时不叠底背驰、有买点时不叠顶背驰，避免「类二卖｜底背驰」自相矛盾。
    """
    parts: list[str] = []
    buy_types = [
        str(p.get("type", ""))
        for p in (buy_points or [])
        if isinstance(p, dict) and p.get("type")
    ]
    sell_types = [
        str(p.get("type", ""))
        for p in (sell_points or [])
        if isinstance(p, dict) and p.get("type")
    ]
    if buy_types:
        parts.append(f"关注{buy_types[0]}")
    if sell_types:
        parts.append(f"注意{sell_types[0]}")
    if divergence.get("top_divergence") and not buy_types:
        parts.append("顶背驰")
    if divergence.get("bottom_divergence") and not sell_types:
        parts.append("底背驰")
    return "｜".join(parts[:2]) if parts else ""


def _unwrap_chan(chan_result: Any) -> dict[str, Any]:
    if not isinstance(chan_result, dict):
        return {}
    try:
        from trader_shared.chan_core import unwrap_chan
        return unwrap_chan(chan_result) or {}
    except Exception:
        if "chanlun" in chan_result and isinstance(chan_result.get("chanlun"), dict):
            return chan_result["chanlun"]
        return chan_result


def _unwrap_wyck(wyck_result: Any) -> dict[str, Any]:
    if not isinstance(wyck_result, dict):
        return {}
    if "wyckoff" in wyck_result and isinstance(wyck_result.get("wyckoff"), dict):
        return wyck_result["wyckoff"]
    return wyck_result


def _chanlun_midline_timeframe(chanlun_midline: Any) -> str:
    """中线缠论时框：weekly | daily_fallback | …（空=未标注，单测/旧载荷兼容）。"""
    chan = _unwrap_chan(chanlun_midline)
    return str(chan.get("timeframe") or "").strip()


def _chan_dir_for_midline_verdict(chanlun_midline: Any) -> int:
    """中线定论/方向合成用缠论方向。

    BUSINESS.md §2.0 / §2.1：daily_fallback 仅结构展示，禁止驱动中线阶段/定论/方向。
    仅 timeframe==weekly（或未标注兼容载荷）可参与合成。
    """
    tf = _chanlun_midline_timeframe(chanlun_midline)
    if tf == "daily_fallback":
        return 0
    return chanlun_midline_dir(chanlun_midline)


def chanlun_midline_dir(chanlun_midline: Any) -> int:
    """中线定论用缠论方向：与 resolve_chanlun_primary / 短线灯标同源。

    - 买卖点（含类一/类二）与背驰：一律跟主解析，避免「行文类二卖、定论却上涨」。
    - 仅 trend/structure 兜底时：structure_confidence=low → 0（不靠结构词硬翻方向）。
    - 调用方若做中线定论合成，须经 `_chan_dir_for_midline_verdict`（daily_fallback→0）。
    """
    chan = _unwrap_chan(chanlun_midline)
    if not chan:
        return 0

    try:
        from trader_shared.chan_core import resolve_chanlun_primary
        prim = resolve_chanlun_primary(chan)
    except Exception:
        prim = {}
    status = str(prim.get("status") or "none")
    direction = int(prim.get("direction") or 0)

    # 点/背驰 = 引擎真值，定论必须一致（含 conf=1 的类二卖）
    if status in ("point", "divergence"):
        return direction

    # ── P2：无点无背驰时，低置信不靠拉升段/上涨趋势兜底翻转 ──
    if str(chan.get("structure_confidence") or "").lower() == "low":
        return 0
    if direction != 0:
        return direction

    # primary 的 trend 路径主要吃 trend_label；补 structure_type 兜底（矩阵单测/无点场景）
    trend_label = str(chan.get("trend_label") or "")
    st = str(chan.get("structure_type") or "")
    if "下跌" in trend_label or "空" in trend_label or "下跌" in st or "空" in st:
        return -1
    if "上涨" in trend_label or "拉升" in trend_label or "多" in trend_label or "上涨" in st or "多" in st:
        return 1
    return 0


def wyckoff_midline_bias(wyckoff_midline: Any, major_stage: str = "") -> str:
    """strong_bull | strong_bear | neutral（B1A）。

    UT 洗盘豁免只认**周线**威科夫 phase=markup；日线 major_stage 不得洗周线 UT
    （BUSINESS.md §2.0：日线不得冒充中线状态）。major_stage 参数保留兼容，已忽略。

    与打分/展示对齐：
    - timeframe=insufficient → neutral（中线威科夫不参与定论）
    - spring_premature / upthrust_premature → 不升 strong_*（孤立噪声）
    """
    del major_stage  # 日线四阶段不得洗周线 UT
    w = _unwrap_wyck(wyckoff_midline)
    if not w:
        return "neutral"
    # 周线不足 / TR 门控：阶段不参与定论 → 偏置亦中性（与展示「阶段暂定不出」一致）
    if w.get("timeframe") == "insufficient" or w.get("phase_tr_gated"):
        return "neutral"

    # 仅周线 markup：upthrust 可能是正常洗盘，不判 strong_bear
    _wp = str(w.get("phase") or "")
    _upstage = _wp == "markup"
    # 孤立/过早 UT 不抬空；否则 markup 外 UT / BC / SOW 看空
    _ut_bear = bool(w.get("upthrust_signal")) and not w.get("upthrust_premature")
    strong_bear = bool(
        (not _upstage and _ut_bear)
        or w.get("bc_signal")
        or w.get("sow_signal")
    )
    # 孤立/过早/弱弹簧/高量警告不抬 strong_bull；SOS 仍有效
    _spring_bull = (
        bool(w.get("spring_signal"))
        and not w.get("spring_premature")
        and w.get("spring_strength") != "weak"
        and w.get("spring_vol_class") != "high_vol_warning"
    )
    strong_bull = bool(_spring_bull or w.get("sos_signal"))
    # 多信号：strong_bear 优先
    if strong_bear:
        return "strong_bear"
    if strong_bull:
        return "strong_bull"
    return "neutral"


def midline_theory_dirs(
    chanlun_midline: Any = None,
    wyckoff_midline: Any = None,
    major_stage: str = "",
) -> tuple[int, str]:
    """返回 (chan_dir, wyck_bias)。chan_dir 已闸 daily_fallback→0（§2.0）。

    major_stage 保留兼容，已忽略（不得洗周线 UT）。
    """
    del major_stage
    return (
        _chan_dir_for_midline_verdict(chanlun_midline),
        wyckoff_midline_bias(wyckoff_midline),
    )


def _midline_view_from_theory(
    *,
    chanlun_midline: Any = None,
    wyckoff_midline: Any = None,
    weekly_frame: str | None = None,
    major_stage: str = "",
) -> str:
    """中线看法：周线缠+威合成（B1A），禁止四阶段词。

    BUSINESS.md §2.0：daily_fallback 缠论不驱动中线看法/方向。
    major_stage 保留兼容，已忽略（不得洗周线 UT）。
    """
    del major_stage
    if weekly_frame == "破坏":
        return "中线框破坏 · 战略减/清倾向"

    # 看法方向合成：daily_fallback 缠论视为无方向（仅展示）
    chan_dir = _chan_dir_for_midline_verdict(chanlun_midline)
    wyck_bias = wyckoff_midline_bias(wyckoff_midline)
    chan = _unwrap_chan(chanlun_midline)
    st = str(chan.get("structure_type") or "").strip()
    # daily_fallback：结构文案也不进看法（避免日线结构词冒充中线看法）
    if _chanlun_midline_timeframe(chanlun_midline) == "daily_fallback":
        st = ""

    if wyck_bias == "strong_bear":
        return "中线慎跟 · 偏空信号"

    if chan_dir < 0 and wyck_bias == "strong_bull":
        return "中线信号打架 · 暂缓跟踪"

    if chan_dir < 0:
        # 可用 structure_type 主词，不得插入日线 major_stage
        if st and not st.startswith("线段不足") and st != "无结构":
            if "下跌" in st:
                return f"{st} · 暂缓跟踪"
            if "盘整" in st:
                return "盘整偏空 · 暂缓跟踪"
            return f"{st} · 暂缓跟踪"
        return "盘整偏空 · 暂缓跟踪"

    if chan_dir > 0 and wyck_bias != "strong_bear":
        if "上涨" in st:
            return "趋势未坏 · 可跟踪"
        return "结构偏多 · 可跟踪"

    return "中线观察"


def synthesize_midline_verdict(
    chanlun_midline: Any = None,
    wyckoff_midline: Any = None,
    fallback_stage: str = "",
) -> dict:
    """中线定论：威科夫中线阶段 + 周线缠论结构副读合成。

    BUSINESS.md §2.0 Dual-track：
    - 中线「阶段」只听周线威科夫；缠论是结构副读，禁止因「缠论领先」改写 stage。
    - daily_fallback 缠论仅展示，不得驱动 stage / bias / direction。

    bias/confidence 仍可听周线缠论方向提示；stage 在威科夫无方向时钉死威科夫阶段词
    （吸筹/派发/…），不得落成「主升初期/转弱」等缠论抢戏标签。

    Returns:
        {"stage","bias","confidence","source","note","wyck_label","chan_label","wyck_dir","chan_dir"}
    """
    # A2：daily_fallback → chan_dir=0（不定论/不改方向）
    _chan_tf = _chanlun_midline_timeframe(chanlun_midline)
    _chan_display_only = _chan_tf == "daily_fallback"
    chan_dir = _chan_dir_for_midline_verdict(chanlun_midline)  # +1/0/-1
    wyck_bias = wyckoff_midline_bias(wyckoff_midline)    # strong_bull/strong_bear/neutral
    wyck_dir = {"strong_bull": 1, "strong_bear": -1, "neutral": 0}.get(wyck_bias, 0)

    # ── 两源各自独立输出（展示用；daily_fallback 仍可出现在 chan_label）──
    chan = _unwrap_chan(chanlun_midline)
    w = _unwrap_wyck(wyckoff_midline)
    _st = str(chan.get("structure_type") or "无结构") if isinstance(chan, dict) else "无结构"
    _conf = str(chan.get("structure_confidence") or "low") if isinstance(chan, dict) else "low"
    _chan_sig = ""
    try:
        from trader_shared.chan_core import resolve_chanlun_primary
        _prim = resolve_chanlun_primary(chan) if chan else {}
        _chan_sig = str(_prim.get("type_short") or _prim.get("type_raw") or "").strip()
    except Exception:
        _prim = {}
    if not _chan_sig:
        _div = (chan.get("divergence") or {}) if isinstance(chan, dict) else {}
        _chan_sig = (
            "顶背驰" if _div.get("top_divergence")
            else ("底背驰" if _div.get("bottom_divergence") else "无背驰")
        )
    chan_label = f"{_st}·置信{_conf}·{_chan_sig}"
    if _chan_display_only:
        chan_label = f"{chan_label}·日线回退仅展示"
    wyck_label = str(w.get("phase_label") or "无明确阶段") if isinstance(w, dict) else "无明确阶段"

    # ── 威科夫阶段词汇（stage 法源）──
    _PHASE_SHORT = {
        "accumulation_a": "吸筹", "accumulation_b": "吸筹",
        "accumulation_c": "吸筹", "accumulation_d": "吸筹",
        "markup": "主升", "markdown": "主跌",
        "distribution_a": "派发", "distribution_c": "派发", "distribution_d": "派发",
        "none": "无阶段",
    }
    _wp = str(w.get("phase") or "none") if isinstance(w, dict) else "none"
    # 无清晰 TR / 周线不足：阶段不参与定论，文案钉死「无阶段」（勿写「领先」）
    _wyck_gated = bool(
        isinstance(w, dict)
        and (
            w.get("phase_tr_gated")
            or w.get("timeframe") == "insufficient"
            or _wp in ("", "none")
        )
    )
    wyck_phase_short = "无阶段" if _wyck_gated else _PHASE_SHORT.get(_wp, "无阶段")
    _CHAN_WORD = {1: "上涨", 0: "盘整", -1: "下跌"}
    _chan_word = _CHAN_WORD[chan_dir]
    if (
        _chan_sig
        and _chan_sig not in ("无背驰", "暂无买卖点", "暂无信号")
        and chan_dir != 0
    ):
        _chan_word = f"{_chan_word}（{_chan_sig}）"
    elif _chan_display_only:
        _chan_word = "日线回退仅展示"

    # ── stage 钉死周线威科夫短词；矩阵仅驱动 bias/confidence/note ──
    # 法源 BUSINESS.md §2.0：缠论不定中线阶段；禁 (wyck_dir,chan_dir) 改写 stage
    # （旧：吸筹+SOS→主升 / 派发+双空→衰退 等矩阵 remap 已废）
    del fallback_stage  # 不足 →「无阶段」，不再用位置分类冒充阶段
    stage = wyck_phase_short
    key = (wyck_dir, chan_dir)
    if key == (1, 1):
        bias, confidence = "bull", "high"
    elif key == (1, 0):
        bias, confidence = "bull", "mid"
    elif key == (1, -1):
        bias, confidence = "bull", "low"
    elif key == (0, 1):
        bias, confidence = "bull", "mid"
    elif key == (0, -1):
        bias, confidence = "bear", "mid"
    elif key == (-1, 1):
        bias, confidence = "bear", "low"
    elif key == (-1, 0):
        bias, confidence = "bear", "mid"
    elif key == (-1, -1):
        bias, confidence = "bear", "high"
    else:  # (0, 0) 双源皆无明确方向
        bias, confidence = "neutral", "low"

    source = "fallback_position" if key == (0, 0) else "wyckoff+chanlun"

    # 缠论低置信时共振档降一级（更保守）
    if confidence == "high" and _conf == "low":
        confidence = "mid"

    # ── 合成注记：缠论不定阶段，禁止「缠论…领先」改写阶段叙事 ──
    if source == "fallback_position":
        note = f"威科夫{wyck_phase_short} × 缠论{_chan_word} → 双源无明确方向"
    elif confidence == "low":
        note = f"威科夫{wyck_phase_short} × 缠论{_chan_word} → 信号冲突，降置信"
    elif key in ((1, 1), (-1, -1)):
        note = f"威科夫{wyck_phase_short} × 缠论{_chan_word} → 共振"
    elif wyck_dir == 0 and chan_dir != 0:
        # A1：结构副读，不称「领先」
        note = f"威科夫{wyck_phase_short} × 缠论{_chan_word}（结构副读·不定阶段）"
    elif chan_dir == 0 and wyck_dir != 0:
        note = f"威科夫{wyck_phase_short}领先 × 缠论{_chan_word}"
    else:
        note = f"威科夫{wyck_phase_short} × 缠论{_chan_word}"

    return {
        "stage": stage, "bias": bias, "confidence": confidence, "source": source,
        "note": note, "wyck_label": wyck_label, "chan_label": chan_label,
        "wyck_dir": wyck_dir, "chan_dir": chan_dir,
    }


def _assert_no_stage_words(text: str) -> str:
    """防御：看法不得含四阶段词。"""
    if _STAGE_WORDS_RE.search(text or ""):
        # 不应发生；若发生则降级为中性观察
        return "中线观察"
    return text


def _shortline_view(
    scene: str,
    theory_status: str,
    daily_ruling: str,
    chase_ok: bool,
) -> str:
    """短线看法：追不追、冲高/回踩。"""
    sc = str(scene or theory_status or "")
    if any(k in sc for k in ("冲高", "减仓", "高抛")):
        return "不适合追，偏冲高减"
    if "突破确认" in sc:
        return "突破观察，确认后再跟"
    if any(k in sc for k in ("低吸", "防守观察")):
        return "宜等回踩/买点，不宜追高" if not chase_ok else "回踩附近可关注"
    if "不宜追" in daily_ruling or "偏空" in daily_ruling:
        return "不适合追"
    if chase_ok:
        return "短线空间尚可，谨慎参与"
    return "短线观望，不追"


def build_daily_ruling(
    fusion: dict[str, Any] | None = None,
    *,
    scene: str = "",
    theory_status: str = "",
    chase_ok: bool = False,
    gate_action: str = "",
    decision_view: dict[str, Any] | None = None,
    resonance: dict[str, Any] | None = None,
) -> str:
    """日线裁定人话：偏多/偏空/中性 + 宜追|不宜追高|观望。

    出手姿态优先听纪律 / decision_view / 共振档；fusion 分仅作偏多偏空仪表，
    不得单独把 stance 推成「宜追」。
    """
    fusion = fusion or {}
    score = fusion.get("weighted_score")
    try:
        score_f = float(score) if score is not None else 0.0
    except (TypeError, ValueError):
        score_f = 0.0

    action = str(fusion.get("action") or "")
    sc = str(scene or theory_status or "")
    dv = decision_view if isinstance(decision_view, dict) else {}
    res = resonance if isinstance(resonance, dict) else {}
    grade = str(res.get("grade") or "")

    if score_f >= 0.15:
        bias = "偏多"
    elif score_f <= -0.1:
        bias = "偏空"
    else:
        bias = "中性"

    reduce_like = any(k in action for k in ("减仓", "空仓", "止损", "观望"))
    disc_block = gate_action in ("不做", "观望", "减仓", "止损离场", "不新开")
    dv_block = bool(dv) and dv.get("allow_new_recommend") is False
    res_block = grade in ("conflict", "momentum_veto")

    if disc_block or not chase_ok or dv_block or res_block:
        stance = "不宜追高"
    elif bias == "偏多" and chase_ok and dv.get("allow_new_recommend") is True:
        stance = "宜追" if "突破" in sc else "观望"
    else:
        stance = "观望"

    if reduce_like and bias != "偏多":
        stance = "不宜追高"

    return f"{bias}，{stance}"


def build_conclusion_block(
    *,
    major_stage: str = "",
    short_term_momentum: str = "",
    scene: str = "",
    theory_status: str = "",
    regime: str = "",
    mistery_gate: dict[str, Any] | None = None,
    discipline: dict[str, Any] | None = None,
    key_prices: dict[str, Any] | None = None,
    fusion: dict[str, Any] | None = None,
    has_position: bool = False,
    daily_ruling: str | None = None,
    weekly_frame: str | None = None,
    chanlun_midline: Any = None,
    wyckoff_midline: Any = None,
    chanlun_daily: Any = None,
    current_price: float = 0.0,
    **_extra: Any,
) -> dict[str, Any]:
    """组装结论块字段。

    stage_line 钉周线威科夫阶段短词（与 synthesize_midline_verdict 同源）；
    major_stage（日线四阶段）仅供冲突/风险旁注，不得冒充中线阶段行。
    discipline 优先于 mistery_gate（merge 后主字段）；无则回退 gate。
    """
    gate = mistery_gate or {}
    disc = discipline if isinstance(discipline, dict) else {}
    # 优先 discipline；兼容仅传 gate
    if disc:
        gate_action = str(disc.get("action") or gate.get("action") or "观望")
        try:
            cap = float(disc.get("suggested_pct_cap") if disc.get("suggested_pct_cap") is not None
                        else disc.get("position_cap_pct") if disc.get("position_cap_pct") is not None
                        else gate.get("position_cap_pct") or 0)
        except (TypeError, ValueError):
            cap = float(gate.get("position_cap_pct") or 0)
    else:
        gate_action = str(gate.get("action") or "观望")
        cap = float(gate.get("position_cap_pct") or 0)
    kp = key_prices or {}
    chase_ok = bool(kp.get("chase_ok"))

    ruling = daily_ruling or build_daily_ruling(
        fusion,
        scene=scene,
        theory_status=theory_status,
        chase_ok=chase_ok,
        gate_action=gate_action,
        decision_view=_extra.get("decision_view") if isinstance(_extra.get("decision_view"), dict) else None,
        resonance=_extra.get("resonance") if isinstance(_extra.get("resonance"), dict) else None,
    )

    mid = _assert_no_stage_words(
        _midline_view_from_theory(
            chanlun_midline=chanlun_midline,
            wyckoff_midline=wyckoff_midline,
            weekly_frame=weekly_frame,
        )
    )
    short = _shortline_view(scene, theory_status, ruling, chase_ok)
    execution = gate_action_to_execution_text(
        gate_action,
        has_position=has_position,
        position_cap_pct=cap,
    )

    # 原因：只讲「账」与硬纪律
    line_chase = str(kp.get("line_chase") or "")
    risk_c = kp.get("risk_chase")
    rew_c = kp.get("reward_chase")
    reason_parts: list[str] = []
    if risk_c is not None and rew_c is not None:
        try:
            rc, rw = float(risk_c), float(rew_c)
            if rc > 0 or rw > 0:
                if rw <= rc:
                    reason_parts.append(f"亏{rc:.1f}/赚{rw:.1f}，不划算")
                elif not chase_ok:
                    reason_parts.append("现价偏冲高，纪律不追")
                else:
                    reason_parts.append(f"现价追大约亏 {rc:.1f}、赚 {rw:.1f}")
        except (TypeError, ValueError):
            pass
    if not reason_parts and line_chase and "→" in line_chase:
        tag = line_chase.split("→")[-1].strip()
        if tag and tag != "可考虑":
            reason_parts.append("现价" + tag)
    _hb_src = disc.get("hard_block") if disc.get("hard_block") else gate.get("hard_block")
    if _hb_src and _hb_src != "none":
        hb = str(_hb_src)
        if "H5" in hb or "H6" in hb:
            if not any("不划算" in p for p in reason_parts):
                reason_parts.append("近端空间不划算")
        elif "H1" in hb:
            reason_parts.append("大盘很差")
        elif "H2" in hb:
            reason_parts.append("衰退阶段不做多")
        elif "H3" in hb:
            reason_parts.append("派发不加仓")
        elif "H4" in hb:
            reason_parts.append("止损无法定义")
    # 纪律 notes：优先 discipline.discipline_notes / entry_block_reason
    _dnotes_list: list[str] = []
    if disc.get("discipline_notes"):
        _dnotes_list = [str(x) for x in disc["discipline_notes"] if str(x).strip()]
    _gnotes = str(disc.get("notes") or gate.get("notes") or "")
    if not _dnotes_list and _gnotes:
        _dnotes_list = [x.strip() for x in _gnotes.replace(";", "；").split("；") if x.strip()]
    _entry_block = str(disc.get("entry_block_reason") or "").strip()
    if _entry_block and _entry_block not in reason_parts:
        # 优先展示 entry_block
        if not any(_entry_block[:6] in p for p in reason_parts):
            reason_parts.append(_entry_block)
    for _dn in _dnotes_list:
        if "不在中线回踩区" in _dn and not any("回踩区" in p for p in reason_parts):
            reason_parts.append("现价不在中线回踩区，不新开")
        elif "中线看法偏空" in _dn and not any("中线看法偏空" in p for p in reason_parts):
            reason_parts.append("中线看法偏空，短线买点不作主开仓")
        elif "置信不足" in _dn and not any("置信" in p for p in reason_parts):
            reason_parts.append("置信不足")
        elif "筹码搬家" in _dn and not any("筹码" in p for p in reason_parts):
            reason_parts.append("筹码搬家警告，不新开")
        elif "主力连续流出" in _dn and not any("流出" in p for p in reason_parts):
            reason_parts.append("主力连续流出，不新开")
    # 兼容仅 gate notes
    if "不在中线回踩区" in _gnotes and not any("回踩区" in p for p in reason_parts):
        reason_parts.append("现价不在中线回踩区，不新开")
    if "中线看法偏空" in _gnotes and not any("中线看法偏空" in p for p in reason_parts):
        reason_parts.append("中线看法偏空，短线买点不作主开仓")
    if "置信不足" in _gnotes and not any("置信" in p for p in reason_parts):
        reason_parts.append("置信不足")
    if "筹码搬家" in _gnotes and not any("筹码" in p for p in reason_parts):
        reason_parts.append("筹码搬家警告，不新开")
    if "主力连续流出" in _gnotes and not any("流出" in p for p in reason_parts):
        reason_parts.append("主力连续流出，不新开")
    seen: set[str] = set()
    uniq: list[str] = []
    for p in reason_parts:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    reason = "；".join(uniq) if uniq else "纪律门控"
    if len(uniq) == 1:
        reason = uniq[0]
    elif uniq:
        reason = "，".join(uniq)

    if gate_action in ("不做", "观望"):
        this_week = "不追现价；回买点再谈"
    elif gate_action in ("轻仓试错", "回踩低吸"):
        buy_ref = kp.get("buy_ref")
        this_week = f"只做买点挂单（参考 {buy_ref:.2f}）" if buy_ref else "只做买点挂单"
    elif gate_action == "持有":
        this_week = "持有跟踪，破位再议，不加仓"
    elif gate_action in ("减仓", "止损离场"):
        this_week = "按关键价减仓/止损，不新开"
    else:
        this_week = "观察为主"

    # 冲突说明：中短冲突 + 验收3 缠多 vs 风控
    conflict = ""
    mid_track = "可跟踪" in mid or "未坏" in mid or "偏多" in mid
    mid_weak = any(k in mid for k in ("暂缓", "慎跟", "打架", "偏空", "破坏", "减/清"))
    short_no = (
        any(k in short for k in ("不适合追", "不宜追", "观望，不追"))
        or "不宜追" in ruling
        or "偏空" in ruling
        or any(k in execution for k in ("不买", "不追"))
    )

    # M1：阶段行 = 周线威科夫短词；禁日线 major_stage 写入 stage_line
    _verdict_stage = synthesize_midline_verdict(chanlun_midline, wyckoff_midline).get("stage")
    stage_txt = str(_verdict_stage or "").strip()
    if stage_txt == "None":
        stage_txt = ""
    # 冲突旁注仍可读日线四阶段（风险侧），与中线阶段行分离
    stage_n = str(major_stage or "").strip()
    if stage_n == "None":
        stage_n = ""
    for base in ("蓄势", "主升", "派发", "衰退"):
        if stage_n.startswith(base) or base in stage_n:
            stage_n = base
            break

    risk_sides: list[str] = []
    if stage_n in ("派发", "衰退"):
        risk_sides.append(f"阶段{stage_n}")
    _cm = _extra.get("chip_migration") if isinstance(_extra.get("chip_migration"), dict) else {}
    if _extra.get("chip_migration_warning") or (
        str(_cm.get("warning_level") or "") not in ("", "none", "None")
    ):
        risk_sides.append("筹码搬家警告")
    if _extra.get("fund_flow_outflow_veto") or bool((fusion or {}).get("fund_flow_outflow_veto")):
        risk_sides.append("主力连续流出")
    if "筹码搬家" in _gnotes and "筹码搬家警告" not in risk_sides:
        risk_sides.append("筹码搬家警告")
    if "主力连续流出" in _gnotes and "主力连续流出" not in risk_sides:
        risk_sides.append("主力连续流出")

    if mid_track and risk_sides:
        conflict = f"中线/缠论偏多，但{'/'.join(risk_sides)} → 以风控为准，不新开"
    elif mid_track and short_no:
        conflict = "中线还能看，现价别买"
    elif mid_weak and short_no:
        conflict = "周线偏空，短线也不追"
    elif mid_weak and not short_no:
        conflict = "中线偏空，短线信号不作主开仓"

    # 浪型标注（波段交易提示）
    wave_label = _build_wave_label(chanlun_daily, current=current_price)
    wave_label_mid = _build_wave_label(chanlun_midline, current=current_price)

    return {
        "midline": mid,
        "stage_line": stage_txt,
        "shortline": short,
        "execution": execution,
        "reason": reason,
        "this_week": this_week,
        "conflict": conflict,
        "daily_ruling": ruling,
        "weekly_frame": weekly_frame,
        "wave_label": wave_label,
        "wave_label_mid": wave_label_mid,
    }
