#!/usr/bin/env python3
"""信号追踪:从signals.jsonl自动拉历史价格计算结果。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import warnings
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# ═══════ Signal ID 统一化 ═══════


def make_signal_id(symbol: str, date: str, signal_type: str, price: str) -> str:
    """Generate unified signal ID.

    Uses SHA256 with 4 normalized fields. 16 hex chars = 48 bits of entropy.
    """
    key = f"{symbol}|{date}|{signal_type}|{price}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# ═══════ 旧 API (兼容 review_core) ═══════

# BAD-013: 坏行统计模块级变量（可读不可写）
_bad_line_count: int = 0
_bad_line_last_reason: str = ""
_bad_line_last_lineno: int = -1


LOG_PATH = Path.home() / ".trader" / "signal_log.jsonl"
LOG_DIR = LOG_PATH.parent
VALID_OUTCOMES = {"win", "loss", "expired", "stopped", "unknown"}


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _safe_price(v: Any) -> float:
    """安全提取价格 — 处理 int/float/str/dict 类型。
    dict 类型如 {"price": 64.41} 或 {"current": 12.5} 会提取首个数值字段。
    """
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0
    if isinstance(v, dict):
        for key in ("price", "current", "value", "amount"):
            if key in v:
                try:
                    return float(v[key])
                except (ValueError, TypeError):
                    continue
    return 0.0


def stable_id(skill: str, target: str, date: str, signal_type: str, price: float | None = None) -> str:
    """[已弃用] 旧信号 ID 生成函数。请使用 make_signal_id() 替代。将在 v0.7 中移除。"""
    warnings.warn("stable_id() is deprecated, use make_signal_id() instead", stacklevel=2)
    key = f"{date}::{skill}::{target}::{signal_type}"
    if price is not None:
        key += f"::{price:.2f}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def _create_log_record(sig_id: str, sig_md5: str, skill: str, target: str, symbol: str, signal_type: str, price: float, env_level: str, env_note: str) -> None:
    record = {
        "signal_id_md5": sig_md5,
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
    norm_type = _normalize_signal_type(str(signal_type))
    sig_id = make_signal_id(
        symbol=_normalize_symbol(symbol or ""),
        date=today,
        signal_type=norm_type,
        price=f"{float(price):.2f}" if price else "0.00",
    )
    old_md5 = hashlib.md5(f"{today}::{skill}::{target}::{signal_type}".encode()).hexdigest()[:12]
    _ensure_log_dir()
    
    # Dedup: check signal_id first, then signal_id_md5 for legacy records
    if not LOG_PATH.exists():
        _create_log_record(sig_id, old_md5, skill, target, symbol, signal_type, price, env_level, env_note)
        return sig_id
    
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            if rec.get("signal_id") == sig_id:
                return sig_id
            # Legacy records (pre-dual-field) only have signal_id_md5
            if "signal_id" not in rec and rec.get("signal_id_md5") == old_md5:
                return sig_id
        except json.JSONDecodeError:
            continue
    
    _create_log_record(sig_id, old_md5, skill, target, symbol, signal_type, price, env_level, env_note)
    return sig_id


def fill(signal_id: str, pnl_pct: float, days_held: int = 0, outcome: str = "unknown") -> tuple[bool, str]:
    if outcome not in VALID_OUTCOMES:
        return False, f"invalid outcome: {outcome}"
    # A24: Validate days_held to avoid corrupt data
    if not isinstance(days_held, (int, float)):
        return False, f"invalid days_held: {days_held} (must be integer)"
    if days_held < 0 or days_held > 3650:
        return False, f"invalid days_held: {days_held} (must be 0-3650)"
    if not LOG_PATH.exists():
        return False, "log file not found"
    # A29: splitlines() handles trailing newline cleanly, unlike strip().split("\n")
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
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
        # A27: Write to .tmp then os.replace for atomicity — prevents corruption on crash
        tmp = LOG_PATH.with_name(LOG_PATH.name + ".tmp")
        tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        fd = os.open(str(tmp), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp), str(LOG_PATH))
        return True, "ok"
    return False, "signal_id not found"


def fill_by_target(target: str, pnl_pct: float, days_held: int = 0, outcome: str = "unknown", signal_type: str = "") -> tuple[int, list[str]]:
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
            if signal_type and str(rec.get("signal_type", "")) != signal_type:
                new_lines.append(json.dumps(rec, ensure_ascii=False))
                continue
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
    global _bad_line_count
    if not LOG_PATH.exists():
        return []
    records = []
    _bad_line_count = 0
    for line in LOG_PATH.read_text(encoding="utf-8").strip().split("\n"):
        if not line.strip(): continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            _bad_line_count += 1
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


# ── 信号类型归一化：中文旧名 → v1 英文标准名 ──

_SIGNAL_TYPE_MAP: dict[str, str] = {
    # 中文旧名
    "低吸观察": "low_buy_watch",
    "低吸已触发": "low_buy_triggered",
    "高抛已触发": "high_sell_triggered",
    "高抛观察": "high_sell_watch",
    "持股观望": "hold_observe",
    "增持": "add_position",
    "减仓": "reduce_position",
    "空仓/止损": "stop_loss",
    "防守观察": "defensive_watch",
    "等转强": "wait_for_strength",
    "持仓": "hold",
    "止损": "stop_loss",
    "追涨": "chase_rally",
    "背驰入场": "divergence_entry",
    # 英文旧名/旧版名
    "low_buy": "low_buy_watch",
    "high_sell": "high_sell_watch",
    "wait": "wait_for_confirmation",
    # 英文标准名（保持不变）
    "low_buy_watch": "low_buy_watch",
    "low_buy_triggered": "low_buy_triggered",
    "high_sell_triggered": "high_sell_triggered",
    "high_sell_watch": "high_sell_watch",
    "trigger_expired": "trigger_expired",
    "blocked": "blocked",
    "hold_observe": "hold_observe",
    "add_position": "add_position",
    "reduce_position": "reduce_position",
    "stop_loss": "stop_loss",
    "defensive_watch": "defensive_watch",
    "wait_for_strength": "wait_for_strength",
    "hold": "hold",
    "chase_rally": "chase_rally",
    "divergence_entry": "divergence_entry",
    "track": "track",
    "risk_stop": "risk_stop",
    "reduce": "reduce",
    "observe": "observe",
    "defensive": "defensive",
    "review_result": "review_result",
    "high_sell_watch": "high_sell_watch",
    "low_sell_triggered": "low_sell_triggered",
    "low_sell_watch": "low_sell_watch",
    # Pass-through values — kept explicit to avoid breaking existing signals.
    # If this grows beyond N items, consider formalizing a trigger_type contract.
    # NOTE: "completed_5m_confirm" and "price_confirm" are stored from
    # test_review_backtrack.py samples; they are valid business semantics.
    "completed_5m_confirm": "completed_5m_confirm",
    "price_confirm": "price_confirm",
}

# 反向映射（英文 → 中文），用于日志显示
_SIGNAL_TYPE_REVERSE: dict[str, str] = {v: k for k, v in _SIGNAL_TYPE_MAP.items()}


# ── 信号生命周期状态 ──

SIGNAL_STATUS_VALUES = {"active", "completed", "expired"}

_FORBIDDEN_TRANSITIONS: dict[tuple[str, str], bool] = {
    ("completed", "active"): True,
    ("completed", "expired"): True,
    ("expired", "active"): True,
    ("expired", "completed"): True,
}


def signal_is_trackable(sig: dict) -> bool:
    status = sig.get("status")
    if not status:
        return True
    return status == "active"


def set_signal_status(rec: dict, new_status: str) -> None:
    if new_status not in SIGNAL_STATUS_VALUES:
        raise ValueError(f"Invalid signal status: {new_status}")
    current = rec.get("status")
    if current and (current, new_status) in _FORBIDDEN_TRANSITIONS:
        raise ValueError(
            f"Transition not allowed: {current} \u2192 {new_status}"
        )
    rec["status"] = new_status
    rec["status_updated_at"] = datetime.now().isoformat()


# ═══════ 信号复合 key：(symbol, date, type, price_str) ═══════
# 用于在 signals.jsonl ↔ signal_results.jsonl 之间匹配信号结果
# 格式与现有 4-key 兼容，但封装在统一函数中，便于维护

def _price_from_trigger(sig: dict) -> str | None:
    """从 signal 的 trigger dict 中提取 price 并格式化为 2 位小数。"""
    tp = sig.get("trigger")
    if isinstance(tp, dict):
        p = tp.get("price")
        if p is not None and _safe_price(p) > 0:
            return f"{_safe_price(p):.2f}"
    # fallback: current 字段
    curr = sig.get("current")
    if curr is not None and _safe_price(curr) > 0:
        return f"{_safe_price(curr):.2f}"
    return None


def _make_signal_key(sig: dict) -> tuple[str, str, str, str]:
    """生成信号唯一匹配 key：(symbol, date, type, price_str)
    
    与 signal_results.jsonl 的 4-key 格式完全一致，确保双向匹配。
    """
    nk = _normalize_symbol(str(sig.get("symbol") or ""))
    nd = _norm_date(str(sig.get("trade_date") or str(sig.get("analysis_time", "")).split("T")[0]))
    nt = str(sig.get("signal_type") or "unknown").strip()
    # 如果 signal_type 是中文旧名，归一化为英文
    nt = _SIGNAL_TYPE_MAP.get(nt, nt)
    ps = _price_from_trigger(sig)
    return (nk, nd, nt, ps or "")


def _ensure_result_dir() -> None:
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)


def _norm_date(raw: str) -> str:
    """Normalize date strings to zero-padded YYYY-MM-DD for safe comparison.
    
    Handles non-zero-padded dates like "2025-5-2" → "2025-05-02".
    Handles datetime strings "2025-05-02T14:30:00" → "2025-05-02".
    """
    s = str(raw).split("T")[0].split(" ")[0]
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        pass
    return s[:10]


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
    """Load signals from store, normalizing symbol for matching."""
    global _bad_line_count
    if not STORE_PATH.exists():
        return []
    signals = []
    _bad_line_count = 0
    normalized_query = _normalize_symbol(symbol) if symbol else None
    for line in STORE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try:
            sig = json.loads(line)
        except json.JSONDecodeError:
            _bad_line_count += 1
            continue
        if not isinstance(sig, dict):
            _bad_line_count += 1
            continue
        sig_symbol = str(sig.get("symbol") or "")
        if normalized_query and _normalize_symbol(sig_symbol) != normalized_query:
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
        bars = fetch_qfq_daily(sec, HttpClient(), days=90)
    except (ValueError, KeyError, IOError, ConnectionError):
        return None

    # FIX-T-BIAS-A17: Normalize date keys so "2025-04-01T00:00:00" matches "2025-04-01"
    norm_sig_date = _norm_date(sig_date)
    date_map = {_norm_date(bar.get("date", "")): bar for bar in bars if bar.get("date")}
    signal_bar = date_map.get(norm_sig_date)
    # FIX-T-BIAS-A21: If exact date not found, search ±21 calendar days for nearest trading day
    if signal_bar is None:
        nearest = None
        try:
            sig_dt_search = datetime.strptime(norm_sig_date, "%Y-%m-%d")
            for ad in range(1, 21):
                for delta in (-ad, ad):
                    test = (sig_dt_search + timedelta(days=delta)).strftime("%Y-%m-%d")
                    if test != norm_sig_date and test in date_map:
                        nearest = date_map[test]
                        break
                if nearest is not None:
                    break
        except ValueError:
            pass
        signal_bar = nearest
    if signal_bar is None:
        return None

    sig_price = float(sig.get("trigger", {}).get("price") or sig.get("current") or signal_bar.get("close", 0) or 0)
    # A16: Track price source for debugging silent fallbacks
    _price_source = "unknown"
    if sig.get("trigger", {}).get("price"):
        _price_source = "trigger.price"
    elif sig.get("current"):
        _price_source = "current"
    elif signal_bar.get("close"):
        _price_source = "signal_bar.close"
    if sig_price == 0:
        sig_price = float(signal_bar.get("close", 0) or 0)
        _price_source = "signal_bar.close (fallback)"
    if sig_price <= 0:
        return None

    try:
        sig_dt = datetime.strptime(sig_date, "%Y-%m-%d")
    except ValueError:
        return None

    norm_symbol = _normalize_symbol(symbol)
    norm_type = _normalize_signal_type(sig_type)
    sig_price_str = f"{sig_price:.2f}"

    res: dict[str, Any] = {
        "signal_id": make_signal_id(norm_symbol, norm_sig_date, norm_type, sig_price_str),
        "symbol": symbol, "name": name,
        "signal_date": sig_date, "signal_type": sig_type,
        "fusion_override": sig.get("fusion_override", False),
        "source_skill": skill, "signal_price": round(sig_price, 2),
        "schema_version": 1,
        "result_time": datetime.now().isoformat(),
        "_price_source": _price_source,
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

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    recent = [s for s in signals if _norm_date(str(s.get("trade_date", ""))) >= cutoff]

    # 已存在结果 — 二级降级: signal_id → 4-key(规范化)
    existing_keys_by_id: dict[str, dict] = {}
    existing_keys_4: dict[tuple[str, str, str, str], dict] = {}
    try:
        _ensure_result_dir()
        for line in RESULT_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            try:
                r = json.loads(line)
                raw_date = _norm_date(str(r.get("signal_date", "")))
                raw_type = _normalize_signal_type(str(r.get("signal_type", "")))
                key_symbol = _normalize_symbol(str(r.get("symbol", "")))
                sp = r.get("signal_price")
                price_str = f"{_safe_price(sp):.2f}" if sp is not None and _safe_price(sp) > 0 else ""
                # 1. Primary: signal_id
                sid = r.get("signal_id")
                if sid:
                    existing_keys_by_id[sid] = r
                # 2. Secondary: 4-key (normalized)
                existing_keys_4[(key_symbol, raw_date, raw_type, price_str)] = r
            except (json.JSONDecodeError, ValueError):
                pass
    except OSError:
        pass

    result_lines: list[str] = []
    updated = 0
    skipped = 0
    lifecycle_skipped = 0

    for sig in recent:
        if not signal_is_trackable(sig):
            lifecycle_skipped += 1; continue
        # 1. Try signal_id match first
        if sig.get("signal_id") in existing_keys_by_id:
            skipped += 1; continue
        # 2. Then try 4-key
        key = _make_signal_key(sig)
        if key in existing_keys_4:
            skipped += 1; continue
        result = _compute_results_for_sig(sig)
        if result:
            set_signal_status(sig, "completed")
            result_lines.append(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
            updated += 1

    # FIX-T-BIAS-pre-existing: ensure results dir always exist so test file paths resolve
    _ensure_result_dir()
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
    elif not RESULT_PATH.exists():
        # Create an empty file so consumers (tests) don't get FileNotFoundError
        tmp_path = RESULT_PATH.with_suffix(".jsonl.tmp")
        tmp_path.write_text("", encoding="utf-8")
        fd = os.open(str(tmp_path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp_path), str(RESULT_PATH))

    if updated > 0:
        lines = STORE_PATH.read_text(encoding="utf-8").splitlines()
        new_sig_lines = []
        completed_ids = set()
        for s in recent:
            if s.get("status") == "completed":
                completed_ids.add(s.get("signal_id"))
        for line in lines:
            if not line.strip():
                new_sig_lines.append(line); continue
            sig_rec = json.loads(line)
            if sig_rec.get("signal_id") in completed_ids:
                sig_rec["status"] = "completed"
                sig_rec["status_updated_at"] = datetime.now().isoformat()
            new_sig_lines.append(json.dumps(sig_rec, ensure_ascii=False))
        tmp = STORE_PATH.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(new_sig_lines) + "\n", encoding="utf-8")
        os.replace(str(tmp), STORE_PATH)

    return {"updated": updated, "skipped": skipped, "lifecycle_skipped": lifecycle_skipped}


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


def _normalize_signal_type(raw_type: str) -> str:
    """归一化信号类型：旧名映射为新名，未知名透传。"""
    return _SIGNAL_TYPE_MAP.get(raw_type, raw_type)


def _make_panel(results: list[dict[str, Any]], days_limit: int | None) -> str:
    """生成信号追踪面板"""
    # 所有记录（含 r_5d=None 的失败样本）
    all_records = [r for r in results]
    # 有效记录（r_5d 有数值）
    valid = [r for r in all_records if r.get("r_5d") is not None]
    # 失败样本（r_5d=None）
    unresolved = [r for r in all_records if r.get("r_5d") is None]

    if not valid and not unresolved:
        return "📊 信号追踪面板\n\n无有效结果。"

    total_valid = len(valid)
    total_unresolved = len(unresolved)
    total_all = total_valid + total_unresolved

    if days_limit:
        cutoff = (datetime.now() - timedelta(days=days_limit)).strftime("%Y-%m-%d")
        valid = [r for r in valid if _norm_date(str(r.get("signal_date", ""))) >= cutoff]
        unresolved = [r for r in unresolved if _norm_date(str(r.get("signal_date", ""))) >= cutoff]
        total_valid = len(valid)
        total_unresolved = len(unresolved)
        total_all = total_valid + total_unresolved

    if total_valid == 0 and total_unresolved == 0:
        return f"📊 信号追踪面板\n\n指定时间范围内无结果。"

    ups = [r for r in valid if r.get("outcome") == "up"]
    downs = [r for r in valid if r.get("outcome") == "down"]
    flats = [r for r in valid if r.get("outcome") == "flat"]
    win_rate = round(len(ups) / total_valid * 100, 1) if total_valid > 0 else 0

    # FIX-T-BIAS-08: 中位数 + 百分位数
    r5_vals = [r["r_5d"] for r in valid]
    avg_r5 = round(sum(r5_vals) / total_valid, 1) if total_valid > 0 else 0
    if total_valid > 0:
        sorted_vals = sorted(r5_vals)
        mid = total_valid // 2
        if total_valid % 2 == 0:
            median_r5 = round((sorted_vals[mid - 1] + sorted_vals[mid]) / 2, 1)
        else:
            median_r5 = round(sorted_vals[mid], 1)
        p10 = round(sorted_vals[int(total_valid * 0.1)] if total_valid > 1 else sorted_vals[0], 1)
        p90 = round(sorted_vals[int(total_valid * 0.9)] if total_valid > 1 else sorted_vals[0], 1)
    else:
        median_r5 = 0.0
        p10 = 0.0
        p90 = 0.0

    total_profit = sum(r["r_5d"] for r in ups) if ups else 0
    total_loss = abs(sum(r["r_5d"] for r in downs)) if downs else 0
    pf = round(total_profit / total_loss, 2) if total_loss > 0 else 0

    # FIX-T-BIAS-09: 类别不平衡检测（flat 占比过高）
    imbalance_warn = ""
    if total_valid >= 5:
        flat_pct = round(len(flats) / total_valid * 100, 1)
        if flat_pct > 80:
            imbalance_warn = (
                f"\n⚠️ 【类别不平衡警告】"
                f" {flat_pct}% 的信号结果为 flat（{len(flats)}/{total_valid}），"
                f"阈值可能过高或策略信号缺乏区分度。"
            )

    # FIX-T-BIAS-11: 极端亏损检测
    extreme_loss_warn = ""
    worst_single = None
    for r in valid:
        rv = r.get("r_5d", 0)
        if rv is not None and rv < -50:
            if worst_single is None or rv < worst_single:
                worst_single = rv
    if worst_single is not None:
        extreme_loss_warn = (
            f"\n⚠️ 【极端亏损风险】单信号最大亏损 {worst_single:+.1f}%，"
            f"请检查止损逻辑和异常样本处理。"
        )

    L = [
        "📊 信号追踪面板",
        "",
        f"发出 {total_all} 次信号（有效 {total_valid}，无数据 {total_unresolved}）"
        f" ｜ 5 日后: {len(ups)} 涨 / {len(downs)} 跌 / {len(flats)} 平",
        f"胜率 {win_rate}% ｜ 平均收益 {avg_r5:+.1f}% ｜ 中位数 {median_r5:+.1f}%"
        + (f" ｜ P10={p10:+.1f}% P90={p90:+.1f}%" if total_valid > 3 else ""),
        f"盈亏比 {pf:.2f}",
        "",
    ]

    # FIX-T-BIAS-13: 按信号类型（归一化后）统计
    # NOTE: loop variable is `sig_type`, NOT `st` — `st` refers to signal_tracker module
    # referenced by tests via `import signal_tracker as st`, so we must not shadow it.
    types: dict[str, list] = {}
    for r in valid:
        # 归一化信号类型
        raw_type = str(r.get("signal_type") or "unknown")
        norm_type = _normalize_signal_type(raw_type)
        types.setdefault(norm_type, []).append(r)
    if types:
        L.append("按信号类型:")
        best = sorted(types.items(), key=lambda x: -len(x[1]))[:5]
        for sig_type, recs in best:
            ups_t = sum(1 for r in recs if r.get("outcome") == "up")
            total_t = len(recs)
            wr_t = round(ups_t / total_t * 100, 1) if total_t else 0
            avg_r = round(sum(r["r_5d"] for r in recs) / total_t, 1) if total_t else 0
            L.append(f"  {sig_type}: {total_t}次 → 胜率 {wr_t}%（平均{avg_r:+.1f}%）")
        L.append("")

    # 按融合覆盖分类
    overridden = [r for r in valid if r.get("fusion_override")]
    if overridden:
        not_overridden = [r for r in valid if not r.get("fusion_override")]
        L.append("按融合覆盖:")
        for label, recs in [("融合覆盖", overridden), ("纯 scene", not_overridden)]:
            ups_r = sum(1 for r in recs if r.get("outcome") == "up")
            total_r = len(recs)
            wr_r = round(ups_r / total_r * 100, 1) if total_r else 0
            avg_r = round(sum(r["r_5d"] for r in recs) / total_r, 1) if total_r else 0
            L.append(f"  {label}: {total_r}次 → 胜率 {wr_r}%（平均{avg_r:+.1f}%）")
        L.append("")

    # 按 source_skill 分层统计（FIX-T-BIAS-10）
    skills: dict[str, list] = {}
    for r in valid:
        sk = str(r.get("source_skill") or "unknown")
        skills.setdefault(sk, []).append(r)
    if len(skills) > 1:
        L.append("按数据源 (source_skill):")
        for sk, recs in sorted(skills.items()):
            ups_s = sum(1 for r in recs if r.get("outcome") == "up")
            downs_s = sum(1 for r in recs if r.get("outcome") == "down")
            flats_s = sum(1 for r in recs if r.get("outcome") == "flat")
            total_s = len(recs)
            wr_s = round(ups_s / total_s * 100, 1) if total_s else 0
            avg_r = round(sum(r["r_5d"] for r in recs) / total_s, 1) if total_s else 0
            L.append(f"  {sk}: {total_s}次 → 胜率 {wr_s}%（平均{avg_r:+.1f}% | {ups_s}涨/{downs_s}跌/{flats_s}平）")
        L.append("")

    # 个股
    stocks: dict[str, list] = {}
    for r in valid:
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

    # 失败样本详情（FIX-T-BIAS-01）
    if unresolved:
        L.append("⚠️ 无数据信号 (unresolved):")
        # 按 failure_code 分类
        fail_groups: dict[str, list] = {}
        for r in unresolved:
            fc = r.get("_failure_code") or "no_data"
            fail_groups.setdefault(fc, []).append(r)
        for fc, recs in fail_groups.items():
            names = []
            for r in recs:
                nm = r.get("name", "unknown")
                if r.get("symbol"):
                    nm += f" ({r['symbol']})"
                names.append(nm)
            reason = recs[0].get("_failure_reason", "")
            reason_text = f" - {reason}" if reason else ""
            L.append(f"  {fc}: {len(recs)}次 ({', '.join(names)}){reason_text}")
        L.append("")

    # FIX-T-BIAS-09 + FIX-T-BIAS-11: 添加到建议区块
    imbalance_warn = ""
    if total_valid >= 5:
        flat_pct = round(len(flats) / total_valid * 100, 1)
        if flat_pct > 80:
            imbalance_warn = (
                f"  • 【类别不平衡】{flat_pct}% (≈{len(flats)}/{total_valid}) 的样本为 flat，"
                f"阈值可能过高或信号缺乏区分度。\n"
            )

    extreme_loss_warn = ""
    if worst_single is not None:
        extreme_loss_warn = (
            f"  • 【极端亏损风险】最大单信号亏损 {worst_single:+.1f}%，"
            f"请检查止损逻辑和异常样本处理。\n"
        )

    # 建议
    L.append("⚠️ 建议:")
    if win_rate >= 65 and total_valid >= 20:
        L.append(f"  • 信号整体表现良好（胜率{win_rate}%>65%），当前策略有效")
    elif win_rate >= 50 and total_valid >= 20:
        L.append(f"  • 信号胜率 {win_rate}%：中等水平，建议继续积累样本")
    elif total_valid >= 20:
        L.append(f"  • 信号胜率仅 {win_rate}%：低于随机，需要重新校准策略")
    else:
        L.append(f"  • 样本量仅 {total_valid}，结果仅供参考。建议积累到30次以上再判断")

    if imbalance_warn:
        L.append(f"{imbalance_warn}")
    if extreme_loss_warn:
        L.append(f"{extreme_loss_warn}")

    worst = [(t, recs) for t, recs in types.items() if len(recs) >= 2]
    if worst:
        worst_sorted = sorted(worst, key=lambda x: sum(r["r_5d"] for r in x[1]) / len(x[1]) if x[1] else 0)
        worst_type, worst_recs = worst_sorted[0]
        worst_wr = round(sum(1 for r in worst_recs if r.get("outcome") == "up") / len(worst_recs) * 100, 1)
        if worst_wr < 50:
            L.append(f"  • 信号\"{worst_type}\"表现最差（{len(worst_recs)}次，胜率{worst_wr}%），建议检查阈值")

    return "\n".join(L)


# ═══════ Signal ID Migration Tool ═══════


def _build_signal_id_inputs(result_rec: dict) -> tuple[str, str, str, str]:
    """Extract normalized inputs for make_signal_id from a signal or result record.

    Works for both signal dict (signals.jsonl) and result dict (signal_results.jsonl).
    Price priority: trigger.price > current > signal_price > "0.00".
    Date field: trade_date (signal) or signal_date (result).
    """
    norm_symbol = _normalize_symbol(str(result_rec.get("symbol", ""))) or ""

    # Price priority: trigger.price > current > signal_price > "0.00"
    if result_rec.get("trigger", {}).get("price"):
        price_str = f"{float(result_rec['trigger']['price']):.2f}"
    elif result_rec.get("current"):
        price_str = f"{float(result_rec['current']):.2f}"
    elif result_rec.get("signal_price"):
        price_str = f"{float(result_rec['signal_price']):.2f}"
    else:
        price_str = "0.00"

    # date field may be trade_date (signal) or signal_date (result)
    date_val = result_rec.get("trade_date") or result_rec.get("signal_date", "")
    norm_date_val = _norm_date(str(date_val)) or ""
    norm_type = _normalize_signal_type(str(result_rec.get("signal_type", "unknown")))

    return norm_symbol, norm_date_val, norm_type, price_str


def _migrate_file(file_path: Path, is_signal: bool = True) -> dict[str, int]:
    """Migrate a single JSONL file. Returns migrated/skipped counts.

    Idempotent: records with signal_id are skipped. Bad lines pass through unchanged.
    """
    if not file_path.exists():
        return {"migrated": 0, "skipped": 0}

    lines_raw = file_path.read_text(encoding="utf-8").splitlines()
    new_lines: list[str] = []
    migrated = 0
    skipped = 0

    for line in lines_raw:
        if not line.strip():
            new_lines.append(line)
            continue

        try:
            rec = json.loads(line)
            if not isinstance(rec, dict):
                new_lines.append(line)
                continue
        except (json.JSONDecodeError, ValueError):
            new_lines.append(line)  # Bad lines pass through
            continue

        if rec.get("signal_id"):
            new_lines.append(line)
            skipped += 1
            continue

        norm = _build_signal_id_inputs(rec)
        rec["signal_id"] = make_signal_id(*norm)
        new_lines.append(json.dumps(rec, ensure_ascii=False))
        migrated += 1

    if migrated > 0:
        tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
        tmp_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        fd = os.open(str(tmp_path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp_path), str(file_path))

    return {"migrated": migrated, "skipped": skipped}


def migrate_signal_ids(store_path: Path | None = None,
                       results_path: Path | None = None) -> dict[str, int]:
    """Add signal_id to existing records in signals.jsonl and signal_results.jsonl.

    Idempotent: records that already carry signal_id are skipped.
    Does NOT process signal_log.jsonl (old MD5 signal_id is irreversible).

    Usage:
        python -c "from signal_tracker import migrate_signal_ids; migrate_signal_ids()"

    Returns:
        dict with keys "signals_migrated", "signals_skipped",
                        "results_migrated", "results_skipped"
    """
    if store_path is None:
        store_path = STORE_PATH
    if results_path is None:
        results_path = RESULT_PATH

    sig_result = _migrate_file(store_path, is_signal=True)
    res_result = _migrate_file(results_path, is_signal=False)

    return {
        "signals_migrated": sig_result["migrated"],
        "signals_skipped": sig_result["skipped"],
        "results_migrated": res_result["migrated"],
        "results_skipped": res_result["skipped"],
    }


def backfill_signal_status() -> dict[str, int]:
    """为已有结果记录的信号补充 status=completed。
    
    幂等：已有 status 的记录跳过。无结果匹配的信号保留 implicit active。
    """
    if not STORE_PATH.exists():
        return {"updated": 0}
    
    result_ids: set[str] = set()
    if RESULT_PATH.exists():
        for line in RESULT_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                if r.get("signal_id"):
                    result_ids.add(r["signal_id"])
            except (json.JSONDecodeError, ValueError):
                continue
    
    if not result_ids:
        return {"updated": 0}
    
    lines = STORE_PATH.read_text(encoding="utf-8").splitlines()
    new_lines = []
    updated = 0
    
    for line in lines:
        if not line.strip():
            new_lines.append(line)
            continue
        try:
            sig = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            new_lines.append(line)
            continue
        
        if sig.get("status"):
            new_lines.append(line)
            continue
        if sig.get("signal_id") in result_ids:
            sig["status"] = "completed"
            sig["status_updated_at"] = datetime.now().isoformat()
            new_lines.append(json.dumps(sig, ensure_ascii=False))
            updated += 1
        else:
            new_lines.append(line)
    
    if updated:
        tmp = STORE_PATH.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        os.replace(str(tmp), STORE_PATH)
    
    return {"updated": updated}


# ═══════ CLI ═══════

# FIX-T-BIAS-03: backfill — 强制回溯历史过期信号
def backfill(days_window: int = 365, batch_size: int = 100) -> dict[str, int]:
    """回溯计算过去 N 天内所有未结算信号的结果。"""
    # 重写 cutoff：days_window 天的全窗口
    signals = _load_signals()
    if not signals or HttpClient is None:
        return {"updated": 0, "skipped": 0}

    cutoff = (datetime.now() - timedelta(days=days_window)).strftime("%Y-%m-%d")
    candidates = [s for s in signals if _norm_date(str(s.get("trade_date", ""))) >= cutoff]

    # 已存在结果 — 二级降级: signal_id → 4-key(规范化)
    existing_keys_by_id: dict[str, dict] = {}
    existing_keys_4: dict[tuple[str, str, str, str], dict] = {}
    try:
        _ensure_result_dir()
        for line in RESULT_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            try:
                r = json.loads(line)
                raw_date = _norm_date(str(r.get("signal_date", "")))
                raw_type = _normalize_signal_type(str(r.get("signal_type", "")))
                key_symbol = _normalize_symbol(str(r.get("symbol", "")))
                sp = r.get("signal_price")
                price_str = f"{_safe_price(sp):.2f}" if sp is not None and _safe_price(sp) > 0 else ""
                # 1. Primary: signal_id
                sid = r.get("signal_id")
                if sid:
                    existing_keys_by_id[sid] = r
                # 2. Secondary: 4-key (normalized)
                existing_keys_4[(key_symbol, raw_date, raw_type, price_str)] = r
            except (json.JSONDecodeError, ValueError):
                pass
    except OSError:
        pass

    result_lines: list[str] = []
    updated = 0
    skipped = 0
    lifecycle_skipped = 0

    for sig in candidates:
        if not signal_is_trackable(sig):
            lifecycle_skipped += 1; continue
        # 1. Try signal_id match first
        if sig.get("signal_id") in existing_keys_by_id:
            skipped += 1; continue
        # 2. Then try 4-key
        key = _make_signal_key(sig)
        if key in existing_keys_4:
            skipped += 1; continue
        result = _compute_results_for_sig(sig)
        if result:
            set_signal_status(sig, "completed")
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
        fd = os.open(str(tmp_path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp_path), str(RESULT_PATH))
        _ensure_result_dir()

    if updated > 0:
        lines = STORE_PATH.read_text(encoding="utf-8").splitlines()
        new_sig_lines = []
        completed_ids = set()
        for s in candidates:
            if s.get("status") == "completed":
                completed_ids.add(s.get("signal_id"))
        for line in lines:
            if not line.strip():
                new_sig_lines.append(line); continue
            sig_rec = json.loads(line)
            if sig_rec.get("signal_id") in completed_ids:
                sig_rec["status"] = "completed"
                sig_rec["status_updated_at"] = datetime.now().isoformat()
            new_sig_lines.append(json.dumps(sig_rec, ensure_ascii=False))
        tmp = STORE_PATH.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(new_sig_lines) + "\n", encoding="utf-8")
        os.replace(str(tmp), STORE_PATH)

    return {"updated": updated, "skipped": skipped, "lifecycle_skipped": lifecycle_skipped}


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    p1 = sub.add_parser("check", help="更新最近N天信号结果")
    p1.add_argument("--days", type=int, default=5)
    p2 = sub.add_parser("show", help="显示面板")
    p2.add_argument("--days", type=int, default=None)
    p2.add_argument("--symbol", default=None)
    p3 = sub.add_parser("update", help="计算最近N天信号结果")
    p3.add_argument("--days", type=int, default=5)
    # FIX-T-BIAS-03: backfill 子命令 — 回溯历史过期信号
    p4 = sub.add_parser("backfill", help="回溯计算过去N天内所有未结算信号")
    p4.add_argument("--days", type=int, default=365)
    p4.add_argument("--batch", type=int, default=100, help="批处理大小")
    args = parser.parse_args(args)

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
    elif args.command == "backfill":
        # FIX-T-BIAS-03: 覆盖 check_recent 的 cutoff，允许处理历史信号
        # 临时覆盖 _load_signals 的 cutoff 范围需要 backfill 独立实现
        result = backfill(args.days, getattr(args, "batch", 100))
        updated = result.get("updated", 0)
        skipped = result.get("skipped", 0)
        if updated == 0 and skipped == 0:
            print("无新结果可更新（全部已有）")
        else:
            print(f"回补了 {updated} 条信号结果，跳过 {skipped} 条")
    else:
        parser.print_help()
        return 1
    return 0


def log(skill: str, target: str, symbol: str, signal_type: str, price: float,
        env_level: str = "", env_note: str = "") -> None:
    """Append a signal log record (alias-compatible with the old writer)."""
    log_safe(skill, target, symbol, signal_type, price, env_level, env_note)


def stats_by_type(skill: str) -> dict[str, dict[str, Any]]:
    """Return per-skill stats grouped by signal_type.

    Returns {signal_type: {filled, win, loss, expired, stopped, win_rate}}.
    """
    if not LOG_PATH.exists():
        return {}
    records: list[dict] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        records.append(rec)

    skill_lower = skill.lower()
    result: dict[str, dict[str, Any]] = {}
    for rec in records:
        if rec.get("skill", "").lower() != skill_lower:
            continue
        sig_type = rec.get("signal_type", "unknown")
        if sig_type not in result:
            result[sig_type] = {"filled": 0, "win": 0, "loss": 0, "expired": 0, "stopped": 0, "unknown_count": 0}
        result[sig_type]["filled"] += 1
        outcome = rec.get("outcome", "unknown")
        if outcome == "win":
            result[sig_type]["win"] += 1
        elif outcome == "loss":
            result[sig_type]["loss"] += 1
        elif outcome == "expired":
            result[sig_type]["expired"] += 1
        elif outcome == "stopped":
            result[sig_type]["stopped"] += 1
        else:
            result[sig_type]["unknown_count"] += 1

    for stats in result.values():
        filled = stats["filled"]
        if filled >= 1:
            stats["win_rate"] = round(stats["win"] / filled, 4)
        else:
            stats["win_rate"] = 0.0

    return result


if __name__ == "__main__":
    sys.exit(main())
