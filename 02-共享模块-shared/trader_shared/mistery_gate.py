"""纪律门控层（规则源：decision-subset）。

产品对外名称：出手 / 纪律 / 失效（报告禁止 mi姐、Mistery 人设文案）。
实现模块名历史原因仍为 mistery_gate；只读 Trader 字段 → 输出 gate dict。
禁止改写 major_stage / fusion 分 / support / stop 等状态数字。

规则源：~/.grok/skills/mistery-core/references/decision-subset.md
展示契约：docs/discipline-layer-copy-plan.md
产品骨架：docs/short-midline-report-and-gate-plan.md
拆分：缠相关纪律（回踩区 / mid_view / 筹码资金新开否决 / 缠侧低置信）
      已迁至 chan_discipline.py，经 merge_discipline 只收紧合并。

P1 扩展点（未实现）：
  weekly_frame — 真周 K 完好/紧张/破坏，破坏后战略减/清倾向。
  接入位置：compute_mistery_gate 末尾，用 weekly_frame 再裁切 action/position_cap。
"""
from __future__ import annotations

from typing import Any


# 单票仓位天花板（subset §6）
_POSITION_CAP_CEILING = 50.0

# 动作 → 仓位档（示意区间取上限用于 cap）
_ACTION_POSITION_BAND: dict[str, float] = {
    "不做": 0.0,
    "观望": 0.0,
    "止损离场": 0.0,
    "减仓": 0.0,  # 新开 0；持仓语义由文案层处理
    "轻仓试错": 15.0,
    "回踩低吸": 30.0,
    "持有": 50.0,
}

# 阶段 × 动能 → 动作（趋势票主表，subset §3）
# 行：蓄势/主升/派发/衰退（及偏强/偏弱变体归一）
# 列：走强/修复/震荡/转弱
_STAGE_MOMENTUM_TABLE: dict[str, dict[str, str]] = {
    "蓄势": {
        "走强": "轻仓试错",
        "修复": "观望",  # 等确认 → 观望
        "震荡": "观望",
        "转弱": "观望",
    },
    "主升": {
        "走强": "持有",  # 回踩可加由追高检查降档
        "修复": "回踩低吸",
        "震荡": "观望",
        "转弱": "减仓",
    },
    "派发": {
        "走强": "观望",  # 不参与加
        "修复": "观望",
        "震荡": "减仓",
        "转弱": "止损离场",  # 清/大减
    },
    "衰退": {
        "走强": "不做",
        "修复": "不做",
        "震荡": "不做",
        "转弱": "不做",
    },
}


def _normalize_stage(major_stage: str) -> str:
    """将 major_stage 变体归一到四阶段主类。"""
    s = str(major_stage or "").strip()
    if not s:
        return ""
    # 蓄势偏强/偏弱 → 蓄势
    for base in ("蓄势", "主升", "派发", "衰退"):
        if s.startswith(base) or base in s:
            return base
    # 旧标签兼容
    legacy = {"修复": "蓄势", "走强": "主升", "震荡": "蓄势", "转弱": "衰退"}
    return legacy.get(s, s)


def _normalize_momentum(momentum: str) -> str:
    m = str(momentum or "").strip()
    if m in ("走强", "修复", "震荡", "转弱"):
        return m
    # 兼容含后缀文案
    for label in ("走强", "修复", "震荡", "转弱"):
        if label in m:
            return label
    return m or ""


def _normalize_regime(regime: str) -> str:
    r = str(regime or "").strip()
    if r in ("正常", "偏弱", "很差"):
        return r
    # market_env 可能给 牛市/震荡市/熊市 等
    mapping = {
        "牛市": "正常",
        "健康": "正常",
        "震荡市": "偏弱",
        "震荡": "偏弱",
        "熊市": "很差",
        "未知": "偏弱",
    }
    return mapping.get(r, r if r else "偏弱")


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def _detect_style(
    major_stage: str,
    turnover_rate: float | None,
    volume_ratio: float | None,
    change_pct: float | None,
    notes_extra: list[str],
) -> str:
    """类型闸启发式：趋势 / 情绪 / 不明（subset §2）。"""
    # 高换手 + 急涨急跌 → 情绪
    high_turnover = turnover_rate is not None and turnover_rate >= 15.0
    extreme_move = change_pct is not None and abs(change_pct) >= 7.0
    wild_volume = volume_ratio is not None and volume_ratio >= 3.0

    emotion_hits = sum([high_turnover, extreme_move, wild_volume])
    if emotion_hits >= 2:
        return "情绪"

    # 蓄势/主升且无情绪特征 → 倾向趋势
    stage = _normalize_stage(major_stage)
    if stage in ("蓄势", "主升") and emotion_hits == 0:
        return "趋势"
    if stage in ("派发", "衰退") and emotion_hits == 0:
        return "趋势"

    if emotion_hits == 1:
        notes_extra.append("类型边界模糊，按不明处理")
        return "不明"

    # 缺量能信息时偏不明
    if turnover_rate is None and volume_ratio is None:
        notes_extra.append("缺量能字段，类型降为不明")
        return "不明"

    return "趋势" if stage else "不明"


def _is_chase_high(
    current: float | None,
    support: float | None,
    buy_ref: float | None,
    scene: str,
) -> bool:
    """竖着追高：远离支撑/买点乱追。"""
    if current is None or current <= 0:
        return False
    scene_s = str(scene or "")
    # 冲高类场景
    if any(k in scene_s for k in ("冲高", "突破确认", "高抛", "减仓")):
        if support and support > 0 and current > support * 1.03:
            return True
        if buy_ref and buy_ref > 0 and current > buy_ref * 1.02:
            return True
    # 现价显著高于买点
    if buy_ref and buy_ref > 0 and current >= buy_ref * 1.03:
        return True
    if support and support > 0 and (current - support) / support >= 0.05:
        return True
    return False


def _check_hard_blocks(
    *,
    regime: str,
    stage: str,
    stop: float | None,
    risk: float | None,
    reward_near: float | None,
    min_rr: float,
    scene: str,
    wants_average_down: bool,
    chase_high: bool,
    notes: list[str],
) -> str:
    """H1–H7 硬否决。返回 hard_block code 或 'none'。"""
    blocks: list[str] = []

    if regime == "很差":
        blocks.append("H1")
    if stage == "衰退":
        blocks.append("H2")
    if stage == "派发":
        # H3：不加仓；持仓只减不做加 — 记为 H3，动作由阶段表主导
        blocks.append("H3")
    if stop is None or stop <= 0:
        blocks.append("H4")

    # H5 盈亏比：目标空间 ≤ 止损空间（或 < min_rr * risk）
    if risk is not None and reward_near is not None and risk > 0:
        if reward_near <= risk * min_rr:
            blocks.append("H5")
    elif risk is not None and risk > 0 and reward_near is not None and reward_near <= 0:
        blocks.append("H5")

    # H6 四不做：可做可不做 / 急涨急跌追打 / 止损难设 / 盈亏比差
    h6_reasons = []
    if "H5" in blocks:
        h6_reasons.append("盈亏比差")
    if "H4" in blocks:
        h6_reasons.append("止损难设")
    if chase_high:
        h6_reasons.append("急涨急跌追打")
    # 可做可不做：震荡 + 非明确低吸场景
    if str(scene or "") in ("", "防守观察", "等转强") and stage == "蓄势":
        # 不单独因场景触发 H6，仅在已有其他纪律叠加时标记
        pass
    if len(h6_reasons) >= 2 or (chase_high and "H5" in blocks):
        blocks.append("H6")
        notes.append("四不做：" + "、".join(h6_reasons) if h6_reasons else "四不做")

    if wants_average_down:
        blocks.append("H7")
        notes.append("禁止摊平补仓")

    if not blocks:
        return "none"
    # 组合展示：优先完整列出关键组合
    if "H5" in blocks and "H6" in blocks:
        # 保留组合码供内部
        return "H5+H6" if blocks == ["H5", "H6"] or set(blocks) == {"H5", "H6"} else "+".join(blocks)
    return "+".join(blocks)


def _action_from_table(stage: str, momentum: str, style: str) -> str:
    if not stage:
        return "观望"
    row = _STAGE_MOMENTUM_TABLE.get(stage)
    if not row:
        return "观望"
    mom = momentum if momentum in row else "震荡"
    action = row.get(mom, "观望")
    # 情绪票：持有/回踩可加 → 短线纪律，不「持有待涨」
    if style == "情绪" and action in ("持有", "回踩低吸"):
        return "轻仓试错" if action == "回踩低吸" else "观望"
    # 类型不明 → 不进入标准底仓/加仓
    if style == "不明" and action in ("轻仓试错", "回踩低吸", "持有"):
        return "观望"
    return action


def _apply_520_invalidation(
    *,
    action: str,
    current: float | None,
    ma20: float | None,
    support: float | None,
    stop: float | None,
    theory_status: str,
    notes: list[str],
) -> tuple[str, str]:
    """520 / MA20 持有与失效；无 MA20 时用 stop/support 近似（subset §4）。

    返回 (action, invalidation_text)。
    """
    invalidation_parts: list[str] = []
    used_proxy = ma20 is None or ma20 <= 0

    if used_proxy:
        notes.append("520口径未直接验证(用stop/support近似)")
        if stop and stop > 0:
            invalidation_parts.append(f"跌破止损 {stop:.2f}")
        if support and support > 0:
            invalidation_parts.append(f"失守支撑 {support:.2f}")
        # 价触 stop 或 theory 暂不碰 → 失效
        if theory_status in ("暂不碰", "风险回避", "空仓规避"):
            action = "不做"
            invalidation_parts.append(f"体系结论={theory_status}")
        elif current and stop and stop > 0 and current <= stop:
            action = "止损离场"
        elif current and support and support > 0 and current < support * 0.995:
            if action in ("持有", "回踩低吸", "轻仓试错"):
                action = "减仓"
    else:
        invalidation_parts.append(f"收盘有效跌破MA20({ma20:.2f})且反抽站不回")
        if current and current < ma20 * 0.995:
            # 近似：现价已在 MA20 下 → 中期走坏倾向
            if action in ("持有", "回踩低吸", "轻仓试错"):
                action = "减仓"
                notes.append("现价在MA20下方，中期生命线紧张")
        if stop and stop > 0:
            invalidation_parts.append(f"或跌破止损 {stop:.2f}")

    inv = "；".join(invalidation_parts) if invalidation_parts else "结构失效则离场"
    return action, inv


def _position_cap_for(
    action: str,
    suggested_pct: float | None,
    regime: str,
    hard_block: str,
) -> float:
    band = _ACTION_POSITION_BAND.get(action, 0.0)
    # 硬否决（含 H3 派发不加）→ 新开 cap=0
    if hard_block and hard_block != "none":
        if any(h in hard_block for h in ("H1", "H2", "H3", "H4", "H5", "H6", "H7")):
            band = 0.0

    if action in ("不做", "观望", "止损离场", "减仓"):
        band = 0.0

    # regime=偏弱：试错/低吸再降一档
    if regime == "偏弱" and action in ("轻仓试错", "回踩低吸"):
        band = max(0.0, band * 0.5)  # 15→7.5, 30→15

    suggested = suggested_pct if suggested_pct is not None else band
    try:
        suggested_f = float(suggested)
    except (TypeError, ValueError):
        suggested_f = band

    cap = min(suggested_f, _POSITION_CAP_CEILING, band if band > 0 or action in ("持有",) else 0.0)
    if action == "持有":
        cap = min(suggested_f if suggested_f > 0 else _POSITION_CAP_CEILING, _POSITION_CAP_CEILING)
    if band == 0.0:
        cap = 0.0
    return round(max(0.0, min(cap, _POSITION_CAP_CEILING)), 1)


def _detect_low_confidence(raw: dict[str, Any]) -> tuple[bool, list[str]]:
    """通用低置信：融合 conf / 多空分歧 / 数据 partial。

    缠侧 mid_quality / structure_confidence 已迁至 chan_discipline（避免双砍矛盾）。
    """
    reasons: list[str] = []

    # migrated → chan_discipline:
    # mid_quality partial/insufficient, structure_confidence=low

    if str(raw.get("data_status") or "").lower() == "partial":
        reasons.append("数据partial")

    try:
        dis = raw.get("fusion_disagreement")
        if dis is not None and int(dis) >= 1:
            reasons.append("日线多空分歧")
    except (TypeError, ValueError):
        pass

    # 专家平均 conf < 0.45 视为低
    try:
        fc = raw.get("fusion_confidence")
        if fc is not None and float(fc) < 0.45:
            reasons.append("融合置信偏低")
    except (TypeError, ValueError):
        pass

    if raw.get("low_confidence") is True:
        reasons.append("低置信标记")

    return (len(reasons) > 0, reasons)


def compute_mistery_gate(inputs: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    """计算纪律门控结果（纯函数，只读输入）。

    保留：H1–H7、阶段×动能主表、520/invalidation、style、RR、追高（日线）、
         fusion_disagreement/data_status 低置信。

    已迁出至 chan_discipline（勿在此重复）：
      中线回踩区外、mid_view 偏空、筹码/资金新开否决、缠侧 mid_quality/structure_confidence。

    输入字段（与 subset §0 对齐，均可选但缺则降档）：
      major_stage, short_term_momentum / momentum,
      theory_status / scene, regime,
      current, support, stop, confirm,
      suggested_pct, ma20,
      risk, reward_near（来自 key_prices，用于 H5）,
      buy_ref, turnover_rate, volume_ratio, change_pct,
      wants_average_down, min_rr,
      weekly_frame（P1 预留）,
      data_status, fusion_disagreement, fusion_confidence

    输出（subset §7）：
      hard_block, style, action, invalidation, position_cap_pct, notes
    """
    raw = dict(inputs or {})
    raw.update(kwargs)

    major_stage = str(raw.get("major_stage") or "")
    momentum = str(raw.get("short_term_momentum") or raw.get("momentum") or "")
    theory_status = str(raw.get("theory_status") or raw.get("scene") or "")
    scene = str(raw.get("scene") or theory_status or "")
    regime = _normalize_regime(str(raw.get("regime") or ""))
    stage = _normalize_stage(major_stage)
    mom = _normalize_momentum(momentum)

    current = _to_float(raw.get("current"))
    support = _to_float(raw.get("support"))
    stop = _to_float(raw.get("stop"))
    confirm = _to_float(raw.get("confirm"))
    ma20 = _to_float(raw.get("ma20"))
    buy_ref = _to_float(raw.get("buy_ref"))
    risk = _to_float(raw.get("risk"))
    reward_near = _to_float(raw.get("reward_near"))
    suggested_pct = _to_float(raw.get("suggested_pct"))
    turnover_rate = _to_float(raw.get("turnover_rate"))
    volume_ratio = _to_float(raw.get("volume_ratio"))
    change_pct = _to_float(raw.get("change_pct"))
    wants_average_down = bool(raw.get("wants_average_down", False))
    min_rr = _to_float(raw.get("min_rr"))
    if min_rr is None:
        min_rr = 1.0

    notes_list: list[str] = []

    # 缺关键字段 → 降一档（最多观望/轻仓）
    missing = []
    if not stage:
        missing.append("major_stage")
    if not mom:
        missing.append("momentum")
        mom = "震荡"
    if stop is None:
        missing.append("stop")
    if missing:
        notes_list.append("缺字段降档:" + ",".join(missing))

    # 若未传入 risk/reward，用 current/buy_ref 与 stop/confirm 粗算
    if risk is None and stop is not None and stop > 0:
        ref = buy_ref or support or current
        if ref is not None and ref > stop:
            risk = ref - stop
    if reward_near is None:
        ref = buy_ref or support or current
        target = confirm
        if ref is not None and target is not None and target > ref:
            reward_near = target - ref

    chase = _is_chase_high(current, support, buy_ref, scene)

    hard_block = _check_hard_blocks(
        regime=regime,
        stage=stage,
        stop=stop,
        risk=risk,
        reward_near=reward_near,
        min_rr=min_rr,
        scene=scene,
        wants_average_down=wants_average_down,
        chase_high=chase,
        notes=notes_list,
    )

    style = _detect_style(major_stage, turnover_rate, volume_ratio, change_pct, notes_list)

    action = _action_from_table(stage, mom, style)

    # H3 派发：强制不加仓
    if stage == "派发" and action in ("轻仓试错", "回踩低吸", "持有"):
        action = "观望"
        notes_list.append("派发不加仓")

    # 硬否决覆盖（H3 单独不强制「不做」，允许减仓动作）
    if hard_block != "none":
        if "H1" in hard_block or "H2" in hard_block or "H4" in hard_block:
            action = "不做"
        elif "H5" in hard_block or "H6" in hard_block:
            action = "不做"
        elif "H7" in hard_block:
            action = "不做"
        elif hard_block == "H3" or hard_block.startswith("H3"):
            if action not in ("减仓", "止损离场"):
                # 派发表可能已是减仓；否则观望不新开
                if mom in ("震荡", "转弱"):
                    action = "减仓" if mom == "震荡" else "止损离场"
                else:
                    action = "观望"

    # 追高：非「竖着追高」不加 → 降为观望
    if chase and action in ("轻仓试错", "回踩低吸", "持有"):
        action = "观望"
        notes_list.append("远离买点/支撑，禁止竖着追高")

    # migrated → chan_discipline:
    # 中线回踩区、mid_view 偏空、筹码搬家/资金流出、缠侧 mid_quality/structure_confidence

    # 通用低置信：融合 conf / 分歧 / data_status（可与 chan 重复，merge 取严）
    low_conf, conf_reasons = _detect_low_confidence(raw)
    if low_conf:
        if action == "回踩低吸":
            action = "轻仓试错"
            notes_list.append("置信不足，降一档")
        elif action in ("轻仓试错", "持有"):
            action = "观望"
            notes_list.append("置信不足，轻仓或不动")
        elif action in ("观望", "不做") and not any("置信不足" in n for n in notes_list):
            notes_list.append("置信不足，轻仓或不动")
        for cr in conf_reasons:
            if cr not in "；".join(notes_list):
                notes_list.append(cr)

    # 主升 + 转弱 增强（subset §5）
    if stage == "主升" and mom == "转弱" and style == "趋势":
        action = "减仓"
        notes_list.append("主升动能转弱，减仓提醒")

    action, invalidation = _apply_520_invalidation(
        action=action,
        current=current,
        ma20=ma20,
        support=support,
        stop=stop,
        theory_status=theory_status,
        notes=notes_list,
    )

    # 缺字段最终再压一档
    if missing and action in ("轻仓试错", "回踩低吸", "持有"):
        action = "观望"

    # weekly_frame 破坏主裁在 chan_discipline；gate 仅双保险收紧开仓类
    weekly_frame = raw.get("weekly_frame")
    if str(weekly_frame or "") == "破坏" and action in ("轻仓试错", "回踩低吸", "持有"):
        action = "观望"

    cap = _position_cap_for(action, suggested_pct, regime, hard_block)
    if low_conf and cap > 0:
        cap = round(max(0.0, cap * 0.5), 1)
        if "置信不足" not in "；".join(notes_list):
            notes_list.append("置信不足，仓位降档")

    return {
        "hard_block": hard_block,
        "style": style,
        "action": action,
        "invalidation": invalidation,
        "position_cap_pct": cap,
        "notes": "；".join(notes_list) if notes_list else "",
        "low_confidence": bool(low_conf),
        # 兼容字段：缠侧细则已迁出，固定中性
        "in_midline_pullback": None,
        "mid_view_weak": False,
    }


def gate_action_to_execution_text(
    action: str,
    *,
    has_position: bool = False,
    position_cap_pct: float = 0.0,
) -> str:
    """门控 action → 出手人话（计划 §4.1 映射表）。

    空仓禁止主结论只写「减仓」→ 译为不宜追高/不新开。
    """
    a = str(action or "观望")
    if a in ("不做", "观望"):
        return "现价不买 · 不追"
    if a == "轻仓试错":
        pct = int(position_cap_pct) if position_cap_pct else 10
        return f"可按买点挂 · 仓位{pct}%"
    if a == "回踩低吸":
        pct = int(position_cap_pct) if position_cap_pct else 15
        return f"可按买点挂 · 仓位{pct}%"
    if a == "持有":
        return "持有叙事 · 是否暂停加看日线"
    if a in ("减仓", "止损离场"):
        if not has_position:
            return "不宜追高 · 不新开"
        if a == "止损离场":
            return "止损离场（点位见关键价）"
        return "减仓（点位见关键价）"
    return "现价不买 · 不追"
