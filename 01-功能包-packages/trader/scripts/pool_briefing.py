#!/usr/bin/env python3
"""选股日报生成器。

用法:
    python pool_briefing.py 688248 600519 601899 ...

从命令行读取股票代码列表，调用 build_report 分析每只票，
按推荐买入 / 重点关注 / 暂时不看分组，输出竖排简报。
"""

from __future__ import annotations

import sys
import warnings
from datetime import date

warnings.filterwarnings("ignore")

# ── Path setup ──────────────────────────────────────────────────────
SCRIPT_DIR = __import__("pathlib").Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from trader_shared import light_data as ld
except (ImportError, ModuleNotFoundError):
    # Fallback: try from root
    _d = SCRIPT_DIR
    for _ in range(8):
        if (_d / "trader_shared").is_dir():
            sys.path.insert(0, str(_d))
            break
        _d = _d.parent

from run_analysis import build_report


# ── Classification ─────────────────────────────────────────────────

def classify(r: dict) -> tuple[str, str]:
    """根据分析结果给出 (category, recommendation_text)。"""
    stage = r.get("stage", "")
    fusion = r.get("fusion") or {}
    action = fusion.get("action", "")
    ems = r.get("expma_status") or {}
    em_trend = str(ems.get("trend_label", ""))

    # Buy: 蓄势/主升 + 融合看多/持股观望 + EXPMA多头/震荡(不偏空)
    if stage in ("蓄势", "主升") and action in ("持股观望", "买入", "加仓"):
        if "多头" not in em_trend and "空头" not in em_trend:
            return ("buy", "可建仓")
        elif "多头" in em_trend:
            return ("buy", "可建仓")

    # Watch: 修复/震荡 或 结构强但需要谨慎
    if action in ("减仓", "减仓观望"):
        return ("watch", "⚠️ 融合建议减仓")
    if stage in ("修复",):
        return ("watch", "等转强")
    if stage in ("震荡",):
        return ("watch", "等信号")

    # Skip: 转弱/衰退 或 结构弱 或 融合空仓
    if stage in ("转弱", "衰退") or "空仓" in action:
        return ("skip", "")

    # Default: anything else goes to watch
    return ("watch", "观望")


# ── Signal extraction ──────────────────────────────────────────────

def signal_tags(r: dict) -> tuple[str, str]:
    """返回 (buy_tags, risk_tags) 空格分隔。不含 EXPMA（由调用方加评分）。"""
    buy = []
    risk = []

    # 结构
    fusion = r.get("fusion") or {}
    chan = fusion.get("signals", {}).get("chan", {})
    if isinstance(chan, dict):
        conf = chan.get("confidence", 0)
        if conf >= 0.6:
            buy.append("结构强")
        elif conf < 0.3:
            risk.append("结构弱")
        else:
            risk.append("结构及格")

    # 量价
    wyk = r.get("wyckoff") or {}
    if isinstance(wyk, dict):
        desc = str(wyk.get("description", ""))
        if "放量" in desc and "缩量" not in desc:
            buy.append("量价健康")
        elif "缩量" in desc or "无量" in desc:
            risk.append("量价弱")

    # 筹码
    cc = r.get("chip_current_pct", 0)
    if cc and cc > 60:
        buy.append(f"筹码锁定({int(cc)}%)")

    # MACD
    macd = r.get("macd_status", {})
    if macd and isinstance(macd, dict):
        d = macd.get("diff", 0)
        if d is not None and d > 0:
            buy.append("MACD零轴上")
        elif d is not None and d < 0:
            risk.append("MACD零轴下")

    # 均线
    ma = r.get("ma", {})
    if ma and isinstance(ma, dict):
        ma20 = float(ma.get("20", 0) or 0)
        cur = r.get("current", 0)
        if ma20 > 0 and cur > ma20:
            buy.append("均线多头")
        elif ma20 > 0 and cur < ma20:
            risk.append("均线空头")
        elif ma20 > 0:
            risk.append("均线不明")

    # 融合动作
    action = fusion.get("action", "")
    if action in ("买入", "加仓"):
        buy.append("融合看多")
    elif action in ("空仓/止损",):
        risk.append("融合空仓")

    # EXPMA 排除（由调用方统一输出评分）

    return (" ".join(buy) if buy else "", " ".join(risk) if risk else "")


# ── Output formatting ──────────────────────────────────────────────

def fmt_pool_briefing(stocks: list[str]) -> str:
    """生成选股日报全文。"""
    results = []
    for t in stocks:
        try:
            r = build_report(t.strip())
            if r.get("current", 0) > 0:
                results.append(r)
        except Exception:
            pass

    if not results:
        return "选股日报：无可用数据"

    # Classify
    buy_list = []
    watch_list = []
    skip_list = []
    for r in results:
        cat, rec = classify(r)
        if cat == "buy":
            buy_list.append((r, rec))
        elif cat == "watch":
            watch_list.append((r, rec))
        else:
            skip_list.append((r, rec))

    # Sort each group by fusion weighted_score desc
    def sort_key(item):
        r = item[0]
        f = r.get("fusion") or {}
        return f.get("weighted_score") or 0

    buy_list.sort(key=sort_key, reverse=True)
    watch_list.sort(key=sort_key, reverse=True)
    skip_list.sort(key=sort_key, reverse=True)

    # Market environment
    today = date.today().isoformat()
    market_env = "未知"
    if results:
        env = results[0].get("market_env", {})
        market_env = env.get("level", "未知") if env else "未知"

    # Build output
    lines = []
    lines.append(f"选股日报 — {today} ｜ 大盘{market_env}")

    # ── Buy ──
    if buy_list:
        lines.append("")
        lines.append(f"推荐买入（{len(buy_list)}只）")
        medals = ["\U0001f947", "\U0001f948", "\U0001f949"]
        for i, (r, rec) in enumerate(buy_list):
            lines.append("")
            lines.append(f"{medals[i] if i < 3 else i+1} {r['name']} {r['symbol']} {r['current']:.2f}（{r['change_pct']:+.2f}%）")
            ems = r.get("expma_status") or {}
            em_s = ems.get("total_score", 0)
            stage = r.get("stage", "")
            fusion_action = (r.get("fusion") or {}).get("action", "")
            buy, _ = signal_tags(r)
            res = r.get("resonance") or {}
            res_s = res.get("total_score", 0)
            parts = [stage, fusion_action] + ([buy] if buy else []) + [f"EXPMA{em_s}/10", f"共振{res_s}/10"]
            lines.append(f"  {' '.join(parts)}")
            lines.append(f"  买{r['support']:.2f} 压{r['resistance']:.2f} 损{r['stop']:.2f}")

    # ── Watch ──
    if watch_list:
        lines.append("")
        lines.append(f"重点关注（{len(watch_list)}只）")
        for i, (r, rec) in enumerate(watch_list):
            lines.append("")
            lines.append(f"{i+1} {r['name']} {r['symbol']} {r['current']:.2f}（{r['change_pct']:+.2f}%）")
            ems = r.get("expma_status") or {}
            em_s = ems.get("total_score", 0)
            stage = r.get("stage", "")
            fusion_action = (r.get("fusion") or {}).get("action", "")
            buy, risk = signal_tags(r)
            parts = [stage, fusion_action]
            if buy:
                parts.append(buy)
            if risk:
                parts.append(risk)
            parts.append(f"EXPMA{em_s}/10")
            lines.append(f"  {' '.join(parts)}")
            lines.append(f"  买{r['support']:.2f} 压{r['resistance']:.2f} 损{r['stop']:.2f}")
            if rec:
                lines.append(f"  {rec}")

    # ── Skip ──
    if skip_list:
        lines.append("")
        lines.append(f"暂时不看（{len(skip_list)}只）")
        for i, (r, rec) in enumerate(skip_list):
            lines.append("")
            lines.append(f"{i+1} {r['name']} {r['symbol']} {r['current']:.2f}（{r['change_pct']:+.2f}%）")
            stage = r.get("stage", "")
            fusion_action = (r.get("fusion") or {}).get("action", "")
            _, risk = signal_tags(r)
            parts = [stage, fusion_action]
            if risk:
                parts.append(risk)
            lines.append(f"  {' '.join(parts)}")

    return "\n".join(lines)


# ── Convenience functions for Agent use ─────────────────────────────

def buy_tags(r: dict) -> str:
    """Return positive signal tags for display."""
    buy, _ = signal_tags(r)
    return buy


def run_briefing(targets: list[str]) -> str:
    """主入口：接收股票列表，返回排版好的日报字符串。"""
    return fmt_pool_briefing(targets)


# ── CLI ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    targets = sys.argv[1:]
    if not targets:
        print("用法: python pool_briefing.py 688248 600519 601899 ...")
        sys.exit(1)
    print(run_briefing(targets))
