"""关键价地图 + 人话亏赚两句。

买卖点始终输出，不依赖 has_position。
规则（修毛刺）：
  - 止损 < 买点区 ≤ 现价侧合理位置；买点优先在现价下方
  - 短线卖点必须在现价上方（且尽量高于买点）
  - 波段卖点 ≥ 短线卖点
  - 禁止主报告写 R:R 术语
"""
from __future__ import annotations

from typing import Any


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        x = float(v)
        if x != x or x <= 0:
            return None
        return x
    except (TypeError, ValueError):
        return None


def _round1(x: float) -> float:
    return round(x + 1e-9, 1)


def _round2(x: float) -> float:
    return round(x + 1e-9, 2)


def build_key_prices(
    *,
    current: float | None = None,
    support: float | None = None,
    stop: float | None = None,
    confirm: float | None = None,
    resistance: float | None = None,
    ma20: float | None = None,
    low_zone_lower: float | None = None,
    low_zone_upper: float | None = None,
    key_levels: dict[str, Any] | None = None,
    take: float | None = None,
    **_extra: Any,
) -> dict[str, Any]:
    """构建关键价字段与两句亏赚。"""
    current = _f(current)
    support = _f(support)
    stop = _f(stop)
    confirm = _f(confirm)
    resistance = _f(resistance)
    ma20 = _f(ma20)
    lz_low = _f(low_zone_lower)
    lz_high = _f(low_zone_upper)
    take = _f(take)
    kl = key_levels or {}

    stop_sell = stop

    # ── 买点区：优先「现价下方」的低吸带 ──
    buy_zone_low: float | None = None
    buy_zone_high: float | None = None

    candidates_lo: list[float] = []
    candidates_hi: list[float] = []

    # 1) low_zone 仅当整体在现价下方（或上沿贴近现价）才采用
    if lz_low and lz_high and lz_high >= lz_low:
        if current is None or lz_high <= current * 1.002:
            candidates_lo.append(lz_low)
            candidates_hi.append(lz_high)
        elif lz_low < current:
            # 跨骑现价：裁到现价下
            candidates_lo.append(lz_low)
            candidates_hi.append(min(lz_high, current))

    # 2) support 窄带
    if support:
        band_hi = _round2(support * 1.008)
        band_lo = support
        if stop_sell and band_lo < stop_sell:
            band_lo = stop_sell
        if current is None or band_lo < current:
            candidates_lo.append(band_lo)
            candidates_hi.append(min(band_hi, current) if current else band_hi)

    # 3) stop 上方试探带（最后手段）
    if stop_sell and current and stop_sell < current:
        candidates_lo.append(_round2(stop_sell * 1.002))
        candidates_hi.append(_round2(min(current * 0.995, stop_sell * 1.02 + (current - stop_sell) * 0.35)))

    # 选一组：上沿尽量 < 现价；优先 low_zone，其次支撑窄带
    best: tuple[float, float] | None = None
    best_score = -1
    for idx, (lo, hi) in enumerate(zip(candidates_lo, candidates_hi)):
        if hi < lo:
            continue
        if stop_sell and hi <= stop_sell:
            continue
        if current and lo >= current:
            continue
        if current and hi >= current:
            hi = _round2(current * 0.995)
        if hi < lo:
            continue
        if current and hi >= current:
            continue
        score = 0
        if current and hi < current:
            score += 3
        if stop_sell and lo >= stop_sell * 0.999:
            score += 2
        width_pct = (hi - lo) / max(lo, 1e-9)
        if 0.001 <= width_pct <= 0.03:
            score += 2
        elif width_pct < 0.001:
            score -= 1
        # 靠前的候选（low_zone）略加分
        if idx == 0:
            score += 1
        if score > best_score:
            best = (lo, hi)
            best_score = score

    if best:
        buy_zone_low, buy_zone_high = _round2(best[0]), _round2(best[1])
        if buy_zone_high < buy_zone_low:
            buy_zone_low, buy_zone_high = buy_zone_high, buy_zone_low

    if buy_zone_low is not None and buy_zone_high is not None:
        buy_ref = _round2((buy_zone_low + buy_zone_high) / 2.0)
    elif support and (current is None or support < current):
        buy_ref = support
        buy_zone_low = buy_zone_high = support
    else:
        buy_ref = None

    # ── 短线卖点：必须在现价上方 ──
    sell_candidates: list[float] = []
    for v in (ma20, confirm, resistance, take):
        if v is not None:
            sell_candidates.append(v)
    # key_levels 近端压力
    for k in ("short_resist", "mid_resist"):
        v = _f(kl.get(k))
        if v is not None:
            sell_candidates.append(v)

    floor = current if current else (buy_ref or 0)
    # 短线卖点优先「稍远」的上方结构（MA20/确认），避免贴着现价的噪声压力
    above = sorted({_round2(v) for v in sell_candidates if v > floor * 1.003})
    # 过滤：至少比现价高约 0.8%，否则当噪声
    if current:
        min_up = current * 1.008
        above_pref = [v for v in above if v >= min_up]
        if above_pref:
            above = above_pref

    short_low: float | None = None
    short_high: float | None = None
    if ma20 and ma20 > floor * 1.003 and confirm and confirm >= ma20:
        short_low, short_high = _round2(ma20), _round2(confirm)
        if current and short_low <= current:
            short_low = _round2(max(current * 1.008, ma20))
            short_high = _round2(max(short_low, confirm if confirm > short_low else short_low * 1.01))
    elif len(above) >= 2:
        short_low, short_high = above[0], above[1]
        if (short_high - short_low) / max(short_low, 1e-9) < 0.003 and len(above) >= 3:
            short_high = above[2]
    elif len(above) == 1:
        short_low = short_high = above[0]
    elif buy_ref:
        risk_guess = (buy_ref - stop_sell) if stop_sell and buy_ref > stop_sell else buy_ref * 0.015
        short_low = short_high = _round2(buy_ref + max(risk_guess * 1.5, buy_ref * 0.01))
        if current and short_high <= current:
            short_low = short_high = _round2(current * 1.015)

    short_target = short_high or short_low

    # ── 波段卖点：明显更高的压力 ──
    swing_sell = _f(kl.get("short_resist")) or _f(kl.get("mid_resist")) or resistance
    if swing_sell is None or (short_target and swing_sell <= short_target):
        swing_sell = _f(kl.get("long_resist")) or swing_sell
    if swing_sell is None and short_target:
        swing_sell = _round2(short_target * 1.08)
    if current and swing_sell and swing_sell <= current:
        swing_sell = _f(kl.get("long_resist")) or _round2(current * 1.1)

    far_sell = _f(kl.get("long_resist")) or swing_sell
    if far_sell and swing_sell and far_sell < swing_sell:
        far_sell = swing_sell

    # ── 空间参考用支撑阶梯（地图，非卖点）──
    space_near = _f(kl.get("short_support")) or support
    space_mid = _f(kl.get("mid_support"))
    space_far = _f(kl.get("long_support"))

    # ── 亏赚 ──
    risk_buy = None
    reward_buy = None
    reward_far = None
    if buy_ref is not None and stop_sell is not None:
        risk_buy = max(0.0, buy_ref - stop_sell)
    if buy_ref is not None and short_target is not None:
        reward_buy = max(0.0, short_target - buy_ref)
    if buy_ref is not None and (far_sell or swing_sell) is not None:
        reward_far = max(0.0, (far_sell or swing_sell) - buy_ref)

    risk_chase = None
    reward_chase = None
    if current is not None and stop_sell is not None:
        risk_chase = max(0.0, current - stop_sell)
    if current is not None and short_target is not None:
        reward_chase = max(0.0, short_target - current)

    # 追：赚必须明显大于亏，且现价低于短线卖点
    chase_ok = False
    if (
        risk_chase is not None
        and reward_chase is not None
        and risk_chase > 0
        and reward_chase > risk_chase * 1.2
        and short_target is not None
        and current is not None
        and current < short_target * 0.995
    ):
        chase_ok = True
    # 现价已在买点区上沿附近或上方 → 不叫「在买点」，追句默认不追
    if buy_zone_high and current and current >= buy_zone_high * 0.998:
        if not (reward_chase and risk_chase and reward_chase > risk_chase * 1.5):
            chase_ok = False
    if buy_ref and current and current <= buy_ref * 1.003:
        # 更像挂买点，不是追
        pass

    line_buy = ""
    line_chase = ""
    if buy_ref is not None:
        r1 = _round1(risk_buy or 0)
        e1 = _round1(reward_buy or 0)
        far_price = (far_sell or swing_sell) if (far_sell or swing_sell) else None
        far_label = f"目标{far_price:.2f}" if far_price else f"远看{e1}"
        line_buy = f"{buy_ref:.2f} 买：亏约 {r1} / 赚约 {e1}（{far_label}）"
    if current is not None:
        r2 = _round1(risk_chase or 0)
        e2 = _round1(reward_chase or 0)
        verdict = "可考虑" if chase_ok else "不追"
        line_chase = f"{current:.2f} 追：亏约 {r2} / 赚约 {e2} → {verdict}"

    notes = []
    if not buy_ref:
        notes.append("买点区数据不足")
    if not stop_sell:
        notes.append("止损未定义")
    if short_target and current and short_target <= current:
        notes.append("短线卖点未有效高于现价")

    return {
        "stop_sell": stop_sell,
        "buy_zone_low": buy_zone_low,
        "buy_zone_high": buy_zone_high,
        "buy_ref": buy_ref,
        "short_sell_low": short_low,
        "short_sell_high": short_high,
        "swing_sell": swing_sell,
        "far_sell": far_sell,
        "space_near": space_near,
        "space_mid": space_mid,
        "space_far": space_far,
        "risk": risk_buy,
        "reward_near": reward_buy,
        "reward_far": reward_far,
        "risk_chase": risk_chase,
        "reward_chase": reward_chase,
        "chase_ok": chase_ok,
        "line_buy": line_buy,
        "line_chase": line_chase,
        "notes": "；".join(notes) if notes else "",
    }
