#!/usr/bin/env python3
"""信号追踪:从signals.jsonl自动拉历史价格计算结果。"""
from __future__ import annotations

import argparse
import json
import hashlib
import os
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# ═══════ 旧 API (兼容 review_core) ═══════

# BAD-013: 坏行统计模块级变量（可读不可写）
_bad_line_count: int = 0
_bad_line_last_reason: str = ""
_bad_line_last_lineno: int = -1


LOG_PATH = Path.home() / ".trader" / "signal_log.jsonl"
LOG_DIR = LOG_PATH.parent
VALID_OUTCOMES = {"win", "loss", "expired", "stopped", "unknown", None}


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def stable_id(skill: str, target: str, date: str, signal_type: str) -> str:
    key = f"{date}::{skill}::{target}::{signal_type}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def _create_log_record(sig_id: str, skill: str, target: str, symbol: str, signal_type: str, price: float, env_level: str, env_note: str) -> None:
    record = {
        "signal_id": sig_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "skill": skill, "target": target, "symbol": symbol,
        "signal_type": signal_type, "price": price,
        "env_level": env_level, "env_note": env_note,
        "outcome_pnl_pct": None, "outcome_days": None,
        "outcome": None, "filled_at": None,
    }
    _ensure_log_dir()
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_safe(skill: str, target: str, symbol: str, signal_type: str, price: float,
             env_level: str = "", env_note: str = "") -> str:
    today = _today()
    sig_id = stable_id(skill, target, today, signal_type)
    _ensure_log_dir()
    if not LOG_PATH.exists():
        _create_log_record(sig_id, skill, target, symbol, signal_type, price, env_level, env_note)
        return sig_id
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try:
            if json.loads(line).get("signal_id") == sig_id:
                return sig_id
        except json.JSONDecodeError:
            continue
    _create_log_record(sig_id, skill, target, symbol, signal_type, price, env_level, env_note)
    return sig_id


def fill(signal_id: str, pnl_pct: float, days_held: int = 0, outcome: str = "unknown") -> tuple[bool, str]:
    if outcome not in VALID_OUTCOMES:
        return False, f"invalid outcome: {outcome}"
    if not LOG_PATH.exists():
        return False, "log file not found"
    lines = LOG_PATH.read_text(encoding="utf-8").strip().split("\n")
    found = False
    new_lines = []
    for line in lines:
        if not line.strip(): continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            new_lines.append(line)
            continue
        if rec.get("signal_id") == signal_id:
            rec["outcome_pnl_pct"] = round(pnl_pct, 2)
            rec["outcome_days"] = days_held
            rec["outcome"] = outcome
            rec["filled_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            found = True
        new_lines.append(json.dumps(rec, ensure_ascii=False))
    if found:
        LOG_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True, "ok"
    return False, "signal_id not found"


def fill_by_target(target: str, pnl_pct: float, days_held: int = 0, outcome: str = "unknown") -> tuple[int, list[str]]:
    """兼容 review_core"""
    if not LOG_PATH.exists():
        return 0, []
    raw_text = LOG_PATH.read_text(encoding="utf-8")
    lines = raw_text.strip().split("\n") if raw_text.strip() else []
    updated = []
    new_lines = []
    bad = 0
    for line in lines:
        if not line.strip():
            new_lines.append(line)
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            new_lines.append(line)
            continue
        if rec.get("target") == target and rec.get("outcome_pnl_pct") is None:
            rec["outcome_pnl_pct"] = round(pnl_pct, 2)
            rec["outcome_days"] = days_held
            rec["outcome"] = outcome
            rec["filled_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            updated.append(rec.get("signal_id"))
        new_lines.append(json.dumps(rec, ensure_ascii=False))
    if updated or bad > 0:
        # 原子写 + fsync
        tmp_path = LOG_PATH.with_suffix(".jsonl.tmp")
        tmp_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        fd = os.open(str(tmp_path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp_path), str(LOG_PATH))
    return len(updated), updated


def _load_log_all() -> list[dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    records = []
    for line in LOG_PATH.read_text(encoding="utf-8").strip().split("\n"):
        if not line.strip(): continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records
_load_all = _load_log_all  # 兼容测试


def load_recent(
    target: str = "", symbol: str = "", skill: str = "",
    signal_type: str = "", limit: int = 20,
) -> list[dict[str, Any]]:
    records = _load_log_all()
    filtered = []
    for r in records:
        if target and str(r.get("target") or "") != target:
            continue
        if symbol and str(r.get("symbol") or "") != symbol:
            continue
        if skill and str(r.get("skill") or "") != skill:
            continue
        if signal_type and str(r.get("signal_type") or "") != signal_type:
            continue
        filtered.append(r)
    # FIX-07: 按 timestamp 排序（有 filled_at 也优先）
    filtered.sort(key=lambda r: r.get("filled_at") or r.get("timestamp") or "", reverse=True)
    return filtered[:limit]



# ═══════ 新信号追踪逻辑 ═══════

RESULT_PATH = Path.home() / ".trader" / "signal_results.jsonl"
STORE_PATH = Path.home() / ".trader" / "signals.jsonl"


def _ensure_result_dir() -> None:
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_results() -> list[dict[str, Any]]:
    """从 signal_results.jsonl 读结果（BAD-013: 跟踪坏行计数）"""
    global _bad_line_count, _bad_line_last_lineno, _bad_line_last_reason
    if not RESULT_PATH.exists():
        return []
    results = []
    _bad_line_count = 0  # 每次读取重新计数
    lines = RESULT_PATH.read_text(encoding="utf-8").splitlines()
    for lineno, line in enumerate(lines, start=1):
        if not line.strip(): continue
        try:
            results.append(json.loads(line))
        except (json.JSONDecodeError, ValueError) as e:
            _bad_line_count += 1
            _bad_line_last_lineno = lineno
            _bad_line_last_reason = str(e)
    return results


def _load_signals(symbol: str | None = None) -> list[dict[str, Any]]:
    if not STORE_PATH.exists():
        return []
    signals = []
    for line in STORE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try:
            sig = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(sig, dict):
            continue
        if symbol and str(sig.get("symbol") or "") != symbol:
            continue
        signals.append(sig)
    return signals


try:
    from light_data import resolve_security, fetch_qfq_daily, HttpClient
    try:
        from light_data import to_float
    except ImportError:
        def to_float(v):
            if v is None: return None
            try: return float(str(v).replace(",", ""))
            except: return None
except ImportError:
    HttpClient = None
    resolve_security = None
    fetch_qfq_daily = None
    to_float = lambda v: None


def _compute_results_for_sig(sig: dict) -> dict[str, Any] | None:
    """为一条信号计算结果"""
    if HttpClient is None:
        return None

    symbol = str(sig.get("symbol") or "")
    name = str(sig.get("name") or sig.get("target") or "unknown")
    sig_date = str(sig.get("trade_date") or str(sig.get("analysis_time", "").split("T")[0]))
    sig_type = str(sig.get("signal_type") or "")
    skill = str(sig.get("source_skill") or "trader")

    try:
        # Prefer symbol for accurate security lookup; fall back to name lookup
        if symbol:
            sec = resolve_security(symbol)
        else:
            sec = resolve_security(name)
        bars = fetch_qfq_daily(sec, HttpClient(), days=40)
    except (ValueError, KeyError, IOError, ConnectionError):
        return None

    date_map = {bar.get("date", ""): bar for bar in bars if bar.get("date")}
    signal_bar = date_map.get(sig_date)
    if signal_bar is None:
        return None

    sig_price = float(sig.get("trigger", {}).get("price") or sig.get("current") or signal_bar.get("close", 0) or 0)
    if sig_price == 0:
        sig_price = float(signal_bar.get("close", 0) or 0)
    if sig_price <= 0:
        return None

    try:
        sig_dt = datetime.strptime(sig_date, "%Y-%m-%d")
    except ValueError:
        return None

    res: dict[str, Any] = {
        "symbol": symbol, "name": name,
        "signal_date": sig_date, "signal_type": sig_type,
        "source_skill": skill, "signal_price": round(sig_price, 2),
        "schema_version": 1,
        "result_time": datetime.now().isoformat(),
    }

    for n in (1, 3, 5):
        # 在目标日期附近最多扫描 13 个日历日找最近的交易日数据
        close_price = sig_price
        for add in range(0, 14):
            test = (sig_dt + timedelta(days=n + add)).strftime("%Y-%m-%d")
            if test in date_map:
                close_price = float(date_map[test].get("close", sig_price))
                break
        res[f"close_{n}d"] = close_price
        res[f"r_{n}d"] = round((close_price - sig_price) / sig_price * 100, 2) if sig_price > 0 else 0
        # FIX-01: 极端跳空保护：单日涨跌 >50% 标记异常，不拉坏统计
        if sig_price > 0:
            return_pct = abs(close_price - sig_price) / sig_price
            if return_pct > 0.5:
                res[f"_extreme_{n}d"] = True

    r5 = res["r_5d"]
    atr = to_float(signal_bar.get("atr14") or 0)
    atr_pct_pct = atr / sig_price * 100 if sig_price > 0 else 2.0
    threshold = atr_pct_pct * 0.8
    if r5 > threshold:
        res["outcome"] = "up"
    elif r5 < -threshold:
        res["outcome"] = "down"
    else:
        res["outcome"] = "flat"

    return res


def check_recent(days: int = 5) -> dict[str, int]:
    """检查并更新最近 N 天后信号结果"""
    signals = _load_signals()
    if not signals or HttpClient is None:
        return {"updated": 0, "skipped": 0}

    cutoff = (datetime.now() - timedelta(days=days + 10)).strftime("%Y-%m-%d")
    recent = [s for s in signals if str(s.get("trade_date", "")) >= cutoff]

    # 已存在的结果 (symbol, date, signal_type) as key to support multi-signal same day
    existing_keys: dict[tuple[str, str, str], dict] = {}
    try:
        _ensure_result_dir()
        for line in RESULT_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            try:
                r = json.loads(line)
                key_symbol = _normalize_symbol(r.get("symbol", ""))
                existing_keys[(key_symbol, str(r.get("signal_date")), str(r.get("signal_type", "")))] = r
            except (json.JSONDecodeError, ValueError):
                pass
    except OSError:
        pass

    result_lines: list[str] = []
    updated = 0
    skipped = 0

    for sig in recent:
        nk = _normalize_symbol(sig.get("symbol") or "")
        nd = str(sig.get("trade_date") or "").strip()
        nt = str(sig.get("signal_type") or "").strip()
        key = (nk, nd, nt)
        if key in existing_keys:
            skipped += 1
            continue
        result = _compute_results_for_sig(sig)
        if result:
            result_lines.append(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
            updated += 1

    if result_lines:
        if RESULT_PATH.exists():
            try:
                existing_records = [l for l in RESULT_PATH.read_text(encoding="utf-8").strip().split("\n") if l.strip()]
            except (IOError, OSError):
                existing_records = []
        else:
            existing_records = []
        new_lines = existing_records + result_lines
        tmp_path = RESULT_PATH.with_suffix(".jsonl.tmp")
        tmp_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        # fsync 确保数据落盘
        fd = os.open(str(tmp_path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp_path), str(RESULT_PATH))
        _ensure_result_dir()

    return {"updated": updated, "skipped": skipped}


def show_all(days_limit: int | None = None) -> str:
    """输出面板"""
    results = _load_results()
    return _make_panel(results, days_limit)


def _normalize_symbol(symbol: str) -> str:
    """统一 symbol 格式，避免同票分裂（123456 和 123456.SH 视为相同）。"""
    s = (symbol or "").strip().upper()
    if not s:
        return ""
    if "." in s:
        return s
    if len(s) == 6 and s.isdigit():
        if s.startswith(("6", "9", "5")):
            return f"{s}.SH"
        return f"{s}.SZ"
    return s


def show_single(symbol: str, days_limit: int | None = None) -> str:
    """输出单股面板"""
    normalized = _normalize_symbol(symbol)
    results = [r for r in _load_results() if _normalize_symbol(r.get("symbol", "")) == normalized or (r.get("name") or "").strip().casefold() == symbol.strip().casefold()]
    # BUG-012: 按 result_time 排序取最新，signal_date 可能重复
    results.sort(key=lambda r: r.get("result_time") or r.get("signal_date") or "", reverse=True)
    return _make_panel(results, days_limit)


def _make_panel(results: list[dict[str, Any]], days_limit: int | None) -> str:
    """生成信号追踪面板"""
    filtered = [r for r in results if r.get("r_5d") is not None]
    if not filtered:
        return "📊 信号追踪面板\n\n无有效结果。"

    if days_limit:
        cutoff = (datetime.now() - timedelta(days=days_limit)).strftime("%Y-%m-%d")
        filtered = [r for r in filtered if str(r.get("signal_date", "")) >= cutoff]

    if not filtered:
        return f"📊 信号追踪面板\n\n指定时间范围内无结果。"

    total = len(filtered)
    ups = [r for r in filtered if r.get("outcome") == "up"]
    downs = [r for r in filtered if r.get("outcome") == "down"]
    flats = [r for r in filtered if r.get("outcome") == "flat"]
    win_rate = round(len(ups) / total * 100, 1) if total > 0 else 0

    avg_r5 = round(sum(r["r_5d"] for r in filtered) / total, 1) if total > 0 else 0
    total_profit = sum(r["r_5d"] for r in ups) if ups else 0
    total_loss = abs(sum(r["r_5d"] for r in downs)) if downs else 0
    pf = round(total_profit / total_loss, 2) if total_loss > 0 else 0

    L = [
        "📊 信号追踪面板",
        "",
        f"发出 {total} 次信号 ｜ 5 日后: {len(ups)} 涨 / {len(downs)} 跌 / {len(flats)} 平",
        f"胜率 {win_rate}% ｜ 平均收益 {avg_r5:+.1f}% ｜ 盈亏比 {pf:.2f}",
        "",
    ]

    # 按信号类型
    types: dict[str, list] = {}
    for r in filtered:
        types.setdefault(str(r.get("signal_type") or "unknown"), []).append(r)
    if types:
        L.append("按信号类型:")
        best = sorted(types.items(), key=lambda x: -len(x[1]))[:5]
        for st, recs in best:
            ups_t = sum(1 for r in recs if r.get("outcome") == "up")
            total_t = len(recs)
            wr_t = round(ups_t / total_t * 100, 1) if total_t else 0
            avg_r = round(sum(r["r_5d"] for r in recs) / total_t, 1) if total_t else 0
            L.append(f"  {st}: {total_t}次 → 胜率 {wr_t}%（平均{avg_r:+.1f}%）")
        L.append("")

    # 个股
    stocks: dict[str, list] = {}
    for r in filtered:
        stocks.setdefault(r["name"], []).append(r)
    stock_stats = []
    for name, recs in sorted(stocks.items()):
        ups_s = sum(1 for r in recs if r.get("outcome") == "up")
        total_s = len(recs)
        wr_s = round(ups_s / total_s * 100, 1) if total_s else 0
        avg_r = round(sum(r["r_5d"] for r in recs) / total_s, 1) if total_s else 0
        code = ""
        if recs and recs[0].get("symbol"):
            code = str(recs[0]["symbol"]).replace(".SH", "").replace(".SZ", "")
        stock_stats.append((name, code, total_s, wr_s, avg_r))
    stock_stats.sort(key=lambda x: (-x[3], -x[4]))
    if stock_stats:
        L.append("个股明细:")
        for name, code, total_s, wr_s, avg_r in stock_stats:
            L.append(f"  {'{} ({})'.format(name, code):30s}  样本:{total_s}次  胜率:{wr_s}%  平均{avg_r:+.1f}%")
        L.append("")

    # 建议
    L.append("⚠️ 建议:")
    if win_rate >= 65 and total >= 20:
        L.append(f"  • 信号整体表现良好（胜率{win_rate}%>65%），当前策略有效")
    elif win_rate >= 50 and total >= 20:
        L.append(f"  • 信号胜率 {win_rate}%：中等水平，建议继续积累样本")
    elif total >= 20:
        L.append(f"  • 信号胜率仅 {win_rate}%：低于随机，需要重新校准策略")
    else:
        L.append(f"  • 样本量仅 {total}，结果仅供参考。建议积累到30次以上再判断")

    worst = [(t, recs) for t, recs in types.items() if len(recs) >= 2]
    if worst:
        worst_sorted = sorted(worst, key=lambda x: sum(r["r_5d"] for r in x[1]) / len(x[1]) if x[1] else 0)
        worst_type, worst_recs = worst_sorted[0]
        worst_wr = round(sum(1 for r in worst_recs if r.get("outcome") == "up") / len(worst_recs) * 100, 1)
        if worst_wr < 50:
            L.append(f"  • 信号\"{worst_type}\"表现最差（{len(worst_recs)}次，胜率{worst_wr}%），建议检查阈值")

    return "\n".join(L)


# ═══════ CLI ═══════

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    p1 = sub.add_parser("check", help="更新最近N天信号结果")
    p1.add_argument("--days", type=int, default=5)
    p2 = sub.add_parser("show", help="显示面板")
    p2.add_argument("--days", type=int, default=None)
    p2.add_argument("--symbol", default=None)
    p3 = sub.add_parser("update", help="计算最近N天信号结果")
    p3.add_argument("--days", type=int, default=5)
    args = parser.parse_args()

    if args.command == "check":
        result = check_recent(args.days)
        updated = result.get("updated", 0)
        skipped = result.get("skipped", 0)
        if updated == 0 and skipped == 0:
            print("无新结果可更新（全部已有）")
        else:
            print(f"更新了 {updated} 条信号结果，跳过 {skipped} 条")
    elif args.command == "show":
        if args.symbol:
            print(show_single(args.symbol, args.days))
        else:
            print(show_all(args.days))
    elif args.command == "update":
        result = check_recent(args.days)
        updated = result.get("updated", 0)
        skipped = result.get("skipped", 0)
        if updated == 0 and skipped == 0:
            print("无新结果可更新（全部已有）")
        else:
            print(f"更新了 {updated} 条信号结果，跳过 {skipped} 条")
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
