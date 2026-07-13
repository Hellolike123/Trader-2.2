"""组合策略共振合成：520(米斯特) + 箱体 + 缠论买卖点 + 关键价(支撑压力/止损止盈)。

设计定位（同构于 conclusion_block.synthesize_midline_verdict）：
- 四个原子模块各自负责自己的分析与输出（report_builder 已分别算好
  mistery_gate / box_detect / chanlun 买卖点 / key_prices）。
- 本模块只做最后一步：把四个来源的方向(+1/0/-1)与权重合成一个组合定论
  （buy / hold / sell / watch），并给出共振矩阵与合成买卖点（entry/stop/take）。

所有函数均为纯函数、无网络、无副作用，便于离线单测与等价性门禁。
"""
from __future__ import annotations

from typing import Any, Optional

# 默认权重（用户可调；合成时按「实际参与的模块」重新归一）
_DEFAULT_WEIGHTS: dict[str, float] = {
    "mistery": 0.30,   # 520 持仓体系
    "box": 0.25,       # 箱体突破/破位
    "chan": 0.30,      # 缠论买卖点
    "key": 0.15,       # 关键价结构（支撑压力/止损止盈 RR）
}

# 方向枚举
_BULL = 1
_NEU = 0
_BEAR = -1


# ───────────────────────────────────────────────────────────────────────────
# 各源方向提取（纯函数）
# ───────────────────────────────────────────────────────────────────────────
def _mistery_dir(mistery: Optional[dict]) -> int:
    """520 体系动作 → 方向。

    持有/回踩低吸/轻仓试错 = +1；观望 = 0；减仓/止损离场/不做 = -1。
    """
    if not isinstance(mistery, dict):
        return _NEU
    a = str(mistery.get("action") or "").strip()
    if a in ("持有", "回踩低吸", "轻仓试错"):
        return _BULL
    if a in ("减仓", "止损离场", "不做"):
        return _BEAR
    return _NEU


def _box_dir(box: Optional[dict]) -> int:
    """箱体状态 → 方向。

    突破上沿(up_confirmed/up_pending) = +1；跌破下沿(down_*) = -1；箱体内 = 0。
    """
    if not isinstance(box, dict) or not box.get("found"):
        return _NEU
    st = str(box.get("state") or "")
    if st in ("up_confirmed", "up_pending"):
        return _BULL
    if st in ("down_confirmed", "down_pending"):
        return _BEAR
    return _NEU


def _chan_dir(chan: Optional[dict]) -> int:
    """缠论买卖点 → 方向。

    有买点无卖点 = +1；有卖点无买点 = -1；皆有或皆无 = 0。
    """
    if not isinstance(chan, dict):
        return _NEU
    bp = chan.get("buy_points") or []
    sp = chan.get("sell_points") or []
    has_b = len(bp) > 0
    has_s = len(sp) > 0
    if has_b and not has_s:
        return _BULL
    if has_s and not has_b:
        return _BEAR
    return _NEU


def _key_dir(key: Optional[dict], *, current: Optional[float]) -> int:
    """关键价结构 → 方向。

    现价已触及/跌破止损 = -1（结构失效）；追涨 RR 成立(chase_ok) = +1；否则 0。
    """
    if not isinstance(key, dict) or not current:
        return _NEU
    stop = key.get("stop_sell")
    if stop and current <= stop * 1.003:
        return _BEAR
    if key.get("chase_ok"):
        return _BULL
    return _NEU


# ───────────────────────────────────────────────────────────────────────────
# 合成主函数
# ───────────────────────────────────────────────────────────────────────────
def synthesize_combo_verdict(
    *,
    mistery: Optional[dict] = None,
    box: Optional[dict] = None,
    chan: Optional[dict] = None,
    key: Optional[dict] = None,
    current: Optional[float] = None,
    ma5: Optional[float] = None,
    ma10: Optional[float] = None,
    ma20: Optional[float] = None,
    weights: Optional[dict] = None,
) -> dict:
    """组合策略共振合成定论。

    Args:
        mistery/box/chan/key: 四个原子模块的输出（report_builder 已算好）。
            - mistery: compute_mistery_gate 结果（含 action / position_cap）
            - box: detect_box 结果（含 found / state / top / bottom / stop_loss）
            - chan: {"buy_points": [...], "sell_points": [...]}（levels 中现成）
            - key: build_key_prices 结果（含 stop_sell / buy_zone_* / chase_ok / 各卖点）
        current/ma5/ma10/ma20: 行情上下文（520 与分层用）
        weights: 覆盖默认权重

    Returns:
        {
          "verdict","bias","confidence","score","agree_count","contributing",
          "matrix":[{"name","dir","weight","label"}],
          "entry","stop","take","position_cap","note",
          "sources_present":{...}
        }
    """
    w = dict(_DEFAULT_WEIGHTS)
    if weights:
        w.update({k: float(v) for k, v in weights.items() if k in w})

    sources_present = {
        "mistery": bool(mistery),
        "box": bool(box and box.get("found")),
        "chan": bool(chan),
        "key": bool(key),
    }

    # ── 各源方向 + 展示标签 ──
    d_m = _mistery_dir(mistery)
    d_b = _box_dir(box)
    d_c = _chan_dir(chan)
    d_k = _key_dir(key, current=current)

    _m_label = str(mistery.get("action") or "无") if mistery else "未计算"
    if box and box.get("found"):
        _b_label = str(box.get("state") or "inside")
    else:
        _b_label = "无箱"
    if chan:
        _bp = [str(p.get("type", "")) for p in (chan.get("buy_points") or [])]
        _sp = [str(p.get("type", "")) for p in (chan.get("sell_points") or [])]
        _c_label = f"买[{','.join(_bp) or '-'}]卖[{','.join(_sp) or '-'}]"
    else:
        _c_label = "未计算"
    if key:
        _k_label = "可追" if key.get("chase_ok") else ("破止损" if (key.get("stop_sell") and current and current <= key["stop_sell"] * 1.003) else "结构持有")
    else:
        _k_label = "未计算"

    matrix = [
        {"name": "520体系", "dir": d_m, "weight": w["mistery"], "label": _m_label},
        {"name": "箱体", "dir": d_b, "weight": w["box"], "label": _b_label},
        {"name": "缠论买卖点", "dir": d_c, "weight": w["chan"], "label": _c_label},
        {"name": "关键价", "dir": d_k, "weight": w["key"], "label": _k_label},
    ]

    # ── 加权求和（只累加实际参与的模块）──
    net = 0.0
    total_w = 0.0
    for m in matrix:
        if not sources_present.get(_name_key(m["name"]), False):
            m["weight"] = 0.0
            continue
        net += m["dir"] * m["weight"]
        total_w += m["weight"]
    if total_w > 0:
        net /= total_w  # 归一化到 [-1, 1]

    contributing = sum(1 for m in matrix if m["weight"] > 0)
    # 同向（与 net 同号）模块数
    if net > 0:
        agree_count = sum(1 for m in matrix if m["weight"] > 0 and m["dir"] > 0)
    elif net < 0:
        agree_count = sum(1 for m in matrix if m["weight"] > 0 and m["dir"] < 0)
    else:
        agree_count = 0

    # ── 定论 ──
    verdict, bias, confidence = _resolve_verdict(net, agree_count, contributing)

    # ── 合成买卖点 ──
    entry = _synth_entry(box, key, current)
    stop = _synth_stop(box, key)
    take = _synth_take(box, key)
    position_cap = _synth_position_cap(verdict, confidence, mistery)

    # ── 合成注记 ─
    note = _build_note(matrix, net, verdict, bias, confidence)

    return {
        "verdict": verdict,
        "bias": bias,
        "confidence": confidence,
        "score": round(net, 3),
        "agree_count": agree_count,
        "contributing": contributing,
        "matrix": matrix,
        "entry": entry,
        "stop": stop,
        "take": take,
        "position_cap": position_cap,
        "note": note,
        "sources_present": sources_present,
    }


def _name_key(display_name: str) -> str:
    return {
        "520体系": "mistery",
        "箱体": "box",
        "缠论买卖点": "chan",
        "关键价": "key",
    }.get(display_name, "")


def _resolve_verdict(net: float, agree_count: int, contributing: int) -> tuple[str, str, str]:
    """由净方向与共识度解析定论。"""
    if contributing == 0:
        return "hold", "neutral", "low"

    strong = abs(net) > 0.4
    moderate = abs(net) > 0.15

    if net > 0:
        bias = "bull"
        if strong and agree_count >= 3:
            return "buy", bias, "high"
        if moderate and agree_count >= 2:
            return "watch", bias, "mid"
        if moderate:
            return "watch", bias, "low"
        return "hold", bias, "low"
    if net < 0:
        bias = "bear"
        if strong and agree_count >= 3:
            return "sell", bias, "high"
        if moderate and agree_count >= 2:
            return "watch", bias, "mid"
        if moderate:
            return "watch", bias, "low"
        return "hold", bias, "low"
    return "hold", "neutral", "low"


def _synth_entry(box: Optional[dict], key: Optional[dict], current: Optional[float]) -> Optional[float]:
    """合成入场价：优先箱体下沿回踩 / 关键价买点区；突破态则现价（回踩加仓位=箱体上沿）。"""
    box_found = bool(box and box.get("found"))
    box_state = str(box.get("state") or "") if box else ""

    # 突破确认/待确认：突破位（箱体上沿）回踩即买点；也可现价追
    if box_found and box_state in ("up_confirmed", "up_pending"):
        return _r2(current) if current else _r2(box.get("top"))

    # 箱体内 / 下跌待确认：下沿低吸
    if box_found and box.get("bottom"):
        return _r2(box["bottom"])

    # 回退到关键价买点区
    if key:
        bz = key.get("buy_zone_low")
        if bz:
            return _r2(bz)
        br = key.get("buy_ref")
        if br:
            return _r2(br)
    return _r2(current) if current else None


def _synth_stop(box: Optional[dict], key: Optional[dict]) -> Optional[float]:
    """合成止损：优先箱体结构止损，回退关键价止损。"""
    if box and box.get("found") and box.get("stop_loss"):
        return _r2(box["stop_loss"])
    if key and key.get("stop_sell"):
        return _r2(key["stop_sell"])
    return None


def _synth_take(box: Optional[dict], key: Optional[dict]) -> Optional[float]:
    """合成目标：方向感知的止盈价。

    向上突破（up_confirmed/up_pending）：下一个关键压力位 > 箱体顶，
    若无则用箱体顶 + 箱体高度（测量目标）。
    向下突破（down_*）：箱体底 = 跌破最小目标。
    箱体内：箱体顶作为常规高抛目标。
    无箱体：回退关键价卖点。
    """
    box_found = bool(box and box.get("found"))
    box_state = str(box.get("state") or "") if box else ""

    if box_found:
        box_top = box.get("top")
        box_bot = box.get("bottom")

        # 向上突破：目标 = 关键压力位 > 箱体顶，或测量目标
        if box_state in ("up_confirmed", "up_pending") and box_top:
            if key:
                for f in ("swing_sell", "far_sell", "short_sell_high"):
                    v = key.get(f)
                    if v and v > box_top:
                        return _r2(v)
            # 测量目标：箱体顶 + 箱体高度
            if box_bot and box_top > box_bot:
                return _r2(box_top + (box_top - box_bot))
            return _r2(box_top)

        # 向下突破：目标 = 箱体底
        if box_state in ("down_confirmed", "down_pending") and box_bot:
            return _r2(box_bot)

        # 箱体内：箱体顶（常规高抛位）
        if box_top:
            return _r2(box_top)

    if key:
        for f in ("swing_sell", "far_sell", "short_sell_high"):
            v = key.get(f)
            if v:
                return _r2(v)
    return None


def _synth_position_cap(verdict: str, confidence: str, mistery: Optional[dict]) -> float:
    """合成仓位上限：优先取 520 体系给出的 position_cap；否则按定论/置信推断。"""
    if isinstance(mistery, dict):
        cap = mistery.get("position_cap")
        if isinstance(cap, (int, float)):
            return round(float(cap), 1)
        # 动作直接偏空 → 0
        a = str(mistery.get("action") or "")
        if a in ("减仓", "止损离场", "不做"):
            return 0.0
    if verdict == "buy":
        return 30.0 if confidence == "high" else 15.0
    if verdict == "sell":
        return 0.0
    if verdict == "watch":
        return 10.0 if confidence == "mid" else 0.0
    return 0.0


def _build_note(matrix: list[dict], net: float, verdict: str, bias: str, confidence: str) -> str:
    """生成共振注记。"""
    parts = []
    for m in matrix:
        if m["weight"] == 0:
            continue
        arrow = {1: "多", 0: "中", -1: "空"}[m["dir"]]
        parts.append(f"{m['name']}{arrow}({m['label']})")
    direction_word = {"bull": "看多", "bear": "看空", "neutral": "中性"}[bias]
    conf_word = {"high": "高", "mid": "中", "low": "低"}[confidence]
    return (
        f"共振方向={direction_word}·共识{conf_word}·净分{net:+.2f}｜"
        + "；".join(parts)
    )


def _r2(x: Any) -> Optional[float]:
    try:
        v = float(x)
        return round(v, 2)
    except (TypeError, ValueError):
        return None
