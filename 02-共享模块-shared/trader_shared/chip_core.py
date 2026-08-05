from __future__ import annotations
from typing import Any
from trader_shared._logging import get_logger
from trader_shared.light_data import to_float

_logger = get_logger(__name__)

try:
    from trader_shared.chip_distribution import calc_chip_distribution
except ImportError:
    def calc_chip_distribution(daily, lookback=60):
        return {"peaks": [], "total_volume": 0, "current_pct": None, "mid_price": None}

try:
    from trader_shared.chip_migration_monitor import save_chip_snapshot, check_chip_migration
    _CHIP_MIGRATION_AVAILABLE = True
except ImportError:
    _CHIP_MIGRATION_AVAILABLE = False
    def save_chip_snapshot(target, chip_result, trade_date=None): pass
    def check_chip_migration(target, chip_result, bars=None):
        return {"migration_pct": 0, "warning_level": "none", "warning_text": "", "has_history": False}

def analyze_chips_and_migration(
    bars: list[dict[str, Any]],
    current_price: float,
    target: str,
    trade_date: str | None = None,
    tushare_chip_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """计算筹码分布、识别多周期支撑/阻力价格带以及计算筹码搬家监控结果。"""
    chip = None
    if tushare_chip_data:
        chip = tushare_chip_data
    else:
        try:
            chip = calc_chip_distribution(bars, lookback=60)
            chip["source"] = "internal_calc"
        except Exception as e:
            _logger.debug("Failed to calculate chip distribution: %s", e)

    if not chip:
        chip = {
            "peaks": [],
            "total_volume": 0,
            "current_pct": None,
            "mid_price": None,
            "volume_above_pct": None,
            "bin_width": 0.0,
            "effective_range": (0.0, 0.0),
            "source": "empty_fallback",
        }

    chip_peaks = sorted(chip.get("peaks", []) or [], key=lambda x: x["price"])

    # 筹码搬家监控
    chip_migration = {"migration_pct": 0, "warning_level": "none", "warning_text": "", "has_history": False}
    if _CHIP_MIGRATION_AVAILABLE and chip_peaks:
        try:
            chip_migration = check_chip_migration(target, chip, bars=bars)
            save_chip_snapshot(target, chip, trade_date=trade_date)
        except Exception as e:
            _logger.debug("Failed to check chip migration: %s", e)

    # 支撑/阻力峰值匹配
    chip_support = None
    chip_resistance = None
    if chip_peaks:
        def _peak_strength(p: dict[str, Any]) -> float:
            if _is_cyq_percentile_anchor(p):
                return -1.0
            try:
                return float(p.get("share_of_total") or 0)
            except (TypeError, ValueError):
                return 0.0

        support_peaks = [p for p in chip_peaks if p["price"] < current_price]
        if support_peaks:
            strong_near = sorted(
                [p for p in support_peaks if current_price > 0 and (current_price - p["price"]) / current_price <= 0.03],
                key=_peak_strength,
                reverse=True,
            )
            all_by_strong = sorted(support_peaks, key=_peak_strength, reverse=True)
            if all_by_strong and _peak_strength(all_by_strong[0]) > 2:
                chip_support = all_by_strong[0]["price"]
            elif strong_near and _peak_strength(strong_near[0]) >= 0:
                chip_support = strong_near[0]["price"]
            else:
                # 只剩分位锚时，仍可用最近下方价做参考撑
                real_support = [p for p in support_peaks if not _is_cyq_percentile_anchor(p)]
                chip_support = (real_support or support_peaks)[-1]["price"]

        resistance_peaks = [p for p in chip_peaks if p["price"] > current_price]
        if resistance_peaks:
            strong_near = sorted(
                [p for p in resistance_peaks if current_price > 0 and (p["price"] - current_price) / current_price <= 0.03],
                key=_peak_strength,
                reverse=True,
            )
            all_by_strong = sorted(resistance_peaks, key=_peak_strength, reverse=True)
            if all_by_strong and _peak_strength(all_by_strong[0]) > 2:
                chip_resistance = all_by_strong[0]["price"]
            elif strong_near and _peak_strength(strong_near[0]) >= 0:
                chip_resistance = strong_near[0]["price"]
            else:
                real_res = [p for p in resistance_peaks if not _is_cyq_percentile_anchor(p)]
                chip_resistance = (real_res or resistance_peaks)[0]["price"]

    # 区间边界匹配
    chip_support_lower = None
    chip_support_upper = None
    chip_resistance_lower = None
    chip_resistance_upper = None

    if chip_support is not None and chip_peaks:
        matching_sup = next((p for p in chip_peaks if p["price"] == chip_support), None)
        if matching_sup and "price_lower" in matching_sup and "price_upper" in matching_sup:
            chip_support_lower = matching_sup["price_lower"]
            chip_support_upper = matching_sup["price_upper"]
        else:
            chip_support_lower = chip_support
            chip_support_upper = chip_support

    if chip_resistance is not None and chip_peaks:
        matching_res = next((p for p in chip_peaks if p["price"] == chip_resistance), None)
        if matching_res and "price_lower" in matching_res and "price_upper" in matching_res:
            chip_resistance_lower = matching_res["price_lower"]
            chip_resistance_upper = matching_res["price_upper"]
        else:
            chip_resistance_lower = chip_resistance
            chip_resistance_upper = chip_resistance

    return {
        "chip": chip,
        "chip_peaks": chip_peaks,
        "chip_support": chip_support,
        "chip_resistance": chip_resistance,
        "chip_support_lower": chip_support_lower,
        "chip_support_upper": chip_support_upper,
        "chip_resistance_lower": chip_resistance_lower,
        "chip_resistance_upper": chip_resistance_upper,
        "chip_migration": chip_migration,
    }


# 展示层短标签（人话）；cards / 策略匹配共用，勿各写一套
CHIP_TAG_SUPPORT_WEAK = "下方难撑"
CHIP_TAG_RESIST_WEAK = "上方阻力弱"
CHIP_TAG_TRAPPED_HEAVY = "多数套牢"
CHIP_TAG_TRAPPED_LIGHT = "多数获利"
CHIP_TAG_TRAPPED_MID = "套牢中等"
CHIP_TAG_MIGRATE_HEAVY = "底部大搬"
CHIP_TAG_MIGRATE_WARN = "底部在走"
CHIP_TAG_COST_TIGHT = "成本较齐"
CHIP_TAG_COST_WIDE = "成本较散"

# cyq_perf 分位锚（cost_5/15/50/85/95）用 share_of_total 记分位，不是真实峰占比。
_CYQ_PERCENTILE_SHARES = frozenset({5.0, 15.0, 50.0, 85.0, 95.0})


def _is_cyq_percentile_anchor(peak: dict[str, Any] | None, *, share: float | None = None) -> bool:
    """识别 cyq 分位锚，避免把 50/95 等当成主峰或强撑/压。"""
    if peak is not None and not isinstance(peak, dict):
        return False
    if share is None:
        if not peak:
            return False
        raw = peak.get("share", peak.get("share_of_total"))
        try:
            share = float(raw or 0)
        except (TypeError, ValueError):
            return False
    try:
        share_f = float(share or 0)
    except (TypeError, ValueError):
        return False
    if peak and str(peak.get("kind") or peak.get("peak_kind") or "").lower() in {
        "percentile",
        "cyq_percentile",
        "cost_percentile",
    }:
        return True
    return any(abs(share_f - p) < 1e-6 for p in _CYQ_PERCENTILE_SHARES)


def format_chip_position_light(
    current: float,
    peaks: list[dict[str, Any]] | None = None,
    migration: dict[str, Any] | None = None,
    profit_pct: float | None = None,
) -> str:
    """筹码灯（方案 C，极短，只展示不进 fusion）。

    撑/压 + 主峰位置 + 告警可选（人话短标签）：
      筹码：下方难撑 · 压 44.40
      筹码：撑 50.20 · 压 58.00 · 主峰在 52.10 上方
      筹码：撑 50.20 · 压 58.00 · 主峰在 51.00 附近 · 成本较齐
    不写「多数套牢/多数获利/套牢中等」：主峰在上/下 + 现价关系已够读。
    无警报时不写「底部稳定/未搬家」。
    """
    cur = float(current or 0)
    if cur <= 0:
        return ""  # 调用方跳过空行

    clean: list[dict[str, Any]] = []
    for p in peaks or []:
        if not isinstance(p, dict):
            continue
        try:
            px = float(p.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if px <= 0:
            continue
        try:
            share = float(p.get("share_of_total") or 0)
        except (TypeError, ValueError):
            share = 0.0
        try:
            vol = float(p.get("volume") or 0)
        except (TypeError, ValueError):
            vol = 0.0
        clean.append({"price": px, "share": share, "volume": vol})

    # 无峰：不输出（套牢面已不展示；单靠 profit_pct 不够撑一行）
    if not clean:
        return ""

    below = sorted([x for x in clean if x["price"] < cur], key=lambda x: x["price"])
    above = sorted([x for x in clean if x["price"] > cur], key=lambda x: x["price"])

    parts: list[str] = []

    # 1) 支撑
    if below:
        sup = below[-1]  # 最近下方
        dist_pct = abs(cur - sup["price"]) / cur * 100
        if dist_pct <= 3:
            parts.append(f"撑 {sup['price']:.2f}")
        elif dist_pct <= 10:
            parts.append(f"撑 {sup['price']:.2f}")
        else:
            # 太远：有峰但撑不住现价叙事 → 支撑弱
            parts.append(CHIP_TAG_SUPPORT_WEAK)
    else:
        parts.append(CHIP_TAG_SUPPORT_WEAK)

    # 2) 阻力
    if above:
        res = above[0]
        dist_pct = (res["price"] - cur) / cur * 100
        if dist_pct <= 12:
            parts.append(f"压 {res['price']:.2f}")
        else:
            parts.append(f"压力远 {res['price']:.2f}")
    else:
        parts.append(CHIP_TAG_RESIST_WEAK)

    # 3) 不写套牢面短标签；profit_pct 仍留给 cards/策略
    # 4) 仅告警时追加
    mig = migration if isinstance(migration, dict) else {}
    if mig.get("has_history"):
        level = str(mig.get("warning_level") or "none")
        try:
            mp_f = float(mig.get("migration_pct") or 0)
        except (TypeError, ValueError):
            mp_f = 0.0
        if level in ("clear", "exit", "critical") or mp_f >= 50:
            parts.append(CHIP_TAG_MIGRATE_HEAVY)
        elif level in ("warning", "warn") or mp_f >= 40:
            parts.append(CHIP_TAG_MIGRATE_WARN)

    # 5) 主筹码峰：主峰在哪（相对现价上/下/附近）
    main_peak = _chip_main_peak_tag(clean, cur)
    if main_peak:
        parts.append(main_peak)

    # 6) 成本齐/散（仅 cyq 15/85 分位可判时才写）
    conc = _chip_concentration_tag(clean, cur)
    if conc:
        parts.append(conc)

    return "筹码：" + " · ".join(parts)



def _chip_main_peak_tag(peaks: list[dict[str, Any]], current: float) -> str:
    """主筹码峰短标签：主峰在 X 下方/上方/附近。

    取占比（或 volume）最大的真实峰；跳过全部 cyq 分位锚（5/15/50/85/95）。
    这是「成本堆在哪」的峰思路，不是带宽齐散。
    """
    if not peaks or current <= 0:
        return ""
    cands: list[tuple[float, float, float]] = []  # score, price, share_or_0
    for p in peaks:
        try:
            px = float(p.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if px <= 0:
            continue
        try:
            share = float(p.get("share") or 0)
        except (TypeError, ValueError):
            share = 0.0
        # 分位锚不是「主堆」峰（尤其 50/95 以前会被误当成最大占比）
        if _is_cyq_percentile_anchor(p, share=share):
            continue
        try:
            vol = float(p.get("volume") or 0)
        except (TypeError, ValueError):
            vol = 0.0
        # share 可能是 0~100 的百分比，也可能是 0~1；统一到可比分数
        share_score = share
        if 0 < share_score <= 1.5:
            share_score *= 100.0
        score = share_score if share_score > 0 else vol
        if score <= 0:
            continue
        cands.append((score, px, share_score))
    if not cands:
        return ""
    # 分数最高；同分取离现价更近
    cands.sort(key=lambda x: (-x[0], abs(x[1] - current)))
    _score, px, share_score = cands[0]
    # 太弱的峰不写，避免噪声（占比 <3% 且不是唯一峰时仍写唯一）
    if share_score > 0 and share_score < 3.0 and len(cands) > 1:
        # 若头部明显领先仍可写
        if len(cands) >= 2 and cands[0][0] < cands[1][0] * 1.2:
            return ""
    dist_pct = (px - current) / current * 100.0
    if abs(dist_pct) <= 2.0:
        pos = "附近"
    elif dist_pct < 0:
        pos = "下方"
    else:
        pos = "上方"
    return f"主峰在 {px:.2f} {pos}"


def _chip_concentration_tag(peaks: list[dict[str, Any]], current: float) -> str:
    """根据筹码峰宽度给「成本较齐/成本较散」短标签；判不了就空串。

    只认 cyq 的 15%/85% 成本分位（share_of_total 被标成 15/85）。
    普通支撑/阻力峰不能当成本带宽，否则会把「远阻力」误写成偏发散。
    """
    if not peaks or current <= 0:
        return ""
    p15 = p85 = None
    for p in peaks:
        try:
            share = float(p.get("share") or 0)
            px = float(p.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if px <= 0:
            continue
        # cyq 分位标记：15 / 85（也兼容 kind=percentile）
        if abs(share - 15.0) < 1e-6 or (
            _is_cyq_percentile_anchor(p, share=share)
            and str(p.get("percentile") or p.get("pct") or "") in {"15", "15.0"}
        ):
            p15 = px
        elif abs(share - 85.0) < 1e-6 or (
            _is_cyq_percentile_anchor(p, share=share)
            and str(p.get("percentile") or p.get("pct") or "") in {"85", "85.0"}
        ):
            p85 = px
    if p15 is None or p85 is None or p85 <= p15:
        return ""
    mid = (p15 + p85) / 2.0
    if mid <= 0:
        return ""
    width_pct = (p85 - p15) / mid * 100.0
    if width_pct <= 8.0:
        return CHIP_TAG_COST_TIGHT
    if width_pct >= 20.0:
        return CHIP_TAG_COST_WIDE
    return ""
