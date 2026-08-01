"""Simple file-based cache for historical data (daily bars, fundamentals).

Usage:
    from trader_shared.cache_utils import get_cached, set_cached, get_cached_data

    result = get_cached("daily", "688248", ttl=86400)
    if result is not None:
        data = result.data  # or use get_cached_data("daily", "688248", ttl=86400)
        if result.stale:
            print(f"Warning: data is {result.age_seconds}s old")
    else:
        data = fetch_from_api(...)
        set_cached("daily", "688248", data)
"""
from __future__ import annotations

import atexit
import fcntl
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from trader_shared._logging import get_logger

_logger = get_logger(__name__)

# ── 全局共享线程池 ──────────────────────────────────────────────
# 用于 build_report / load_market_snapshot / cmd_refresh 等场景，
# 避免"cmd_refresh 内建 ThreadPoolExecutor → build_report 内再建 → load_market_snapshot 内再建"的
# 嵌套线程池爆炸（N 只票 × 5 策略 × 3 数据源 × 3 数据源 = N×45 线程竞争）。
# 所有调用者共享同一个 max_workers=5 的池，由 GIL 和任务自然调度管理。

_shared_build_pool: ThreadPoolExecutor | None = None
_shared_build_pool_lock = threading.Lock()


def _shutdown_shared_build_pool() -> None:
    """进程退出时优雅关闭共享线程池。"""
    global _shared_build_pool
    pool, _shared_build_pool = _shared_build_pool, None
    if pool is not None:
        pool.shutdown(wait=True)


atexit.register(_shutdown_shared_build_pool)


def get_shared_build_pool() -> ThreadPoolExecutor:
    """获取全局共享构建线程池（懒加载，双检锁）。

    线程安全：第一次调用时通过锁保证只创建一个实例。
    后续调用直接返回，零开销。
    """
    global _shared_build_pool
    if _shared_build_pool is None:
        with _shared_build_pool_lock:
            if _shared_build_pool is None:
                _shared_build_pool = ThreadPoolExecutor(
                    max_workers=5,
                    thread_name_prefix="trader-build",
                )
    return _shared_build_pool

CACHE_DIR = Path.home() / ".trader" / "cache"

# Subdirectory constants
CACHE_DAILY = "daily"
CACHE_WEEKLY = "weekly"  # 周 K，按自然日 fetch_date 复用
CACHE_MONTHLY = "monthly"  # 月 K，按自然日 fetch_date 复用（共振补拉）
CACHE_ENRICH = "enrich"
CACHE_MARKET_ENV = "market_env"
CACHE_FUND_FLOW = "fund_flow"
CACHE_CYQ = "cyq_perf"  # tushare 筹码日频；按自然日复用

# TTL constants (seconds)
TTL_DAILY = 86400       # 文件年龄兜底；日 K 真正失效看 fetch_date（同日复用）
TTL_WEEKLY = 604800     # 7 days - weekly bars change once per week（旧 TTL；周 K 现优先 fetch_date）
TTL_FUNDAMENTAL = 43200 # 12 hours - shareholder/unlock data updates infrequently
TTL_FUND_FLOW = 86400   # 文件年龄兜底；真正失效看 payload.fetch_date 是否仍是「今天」
TTL_CYQ = 86400 * 3     # 文件年龄兜底；真正失效看 fetch_date
TTL_BARS_DAY = 86400 * 3  # 日/周 K 文件年龄兜底


def _safe_cache_seg(value: str, *, default: str = "unknown") -> str:
    """缓存路径片段：去空白、禁目录穿越，斜杠替换为下划线。"""
    s = str(value or "").strip().replace("/", "_").replace("\\", "_")
    if not s or s in (".", ".."):
        return default
    return s


def daily_bars_cache_target(
    code: str,
    *,
    provider: str,
    adjust: str,
) -> str:
    """日 K 缓存 target：``{provider}/{adjust}/{code}``。

    未复权（tushare daily）与前复权（tencent/akshare qfq）必须分桶，
    禁止共用裸 ``{code}.json`` 互相覆盖。
    """
    return (
        f"{_safe_cache_seg(provider)}/"
        f"{_safe_cache_seg(adjust, default='none')}/"
        f"{_safe_cache_seg(code)}"
    )


def cache_calendar_date() -> str:
    """上海自然日 YYYY-MM-DD（日频缓存的「今天」）。

    前一天的数据可以一直用到换日；换日后再拉网。
    不用交易所日历：周末/节假日首次会多拉一次，拿到仍是上一交易日数据，可接受。
    """
    try:
        from trader_shared.cn_time import today_cn
        return today_cn().isoformat()
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def is_fetch_date_today(payload: Any, today: str | None = None) -> bool:
    """payload 是否带有 fetch_date 且等于今天（同日缓存命中）。"""
    if not isinstance(payload, dict):
        return False
    day = today or cache_calendar_date()
    fd = payload.get("fetch_date")
    return bool(fd) and str(fd)[:10] == day


def unwrap_bars_payload(data: Any) -> list | None:
    """统一解包日缓存：``{fetch_date, rows}`` → list；裸 list 原样返回。"""
    if isinstance(data, dict):
        rows = data.get("rows")
        return list(rows) if isinstance(rows, list) else None
    if isinstance(data, list):
        return list(data)
    return None


def get_day_scoped_bars(
    cache_key: str,
    target: str,
    fetch_fn: Callable[[], list],
    *,
    min_rows: int = 1,
) -> list:
    """日/周 K 等列表：当天第一次 fetch_fn，同日读缓存，换日回源。

    存盘格式：{"fetch_date": "YYYY-MM-DD", "rows": [...]}
    兼容旧缓存（纯 list）：若文件未过期且行数够，仍可用一次，下次写入会带 fetch_date。

    出口统一时间正序（bars[-1]=最新）；倒序缓存会纠正并回写，避免 ATR/MA 中毒。
    """
    today = cache_calendar_date()

    def _finalize(rows: list | None) -> list:
        if not isinstance(rows, list):
            return []
        if len(rows) < min_rows:
            return list(rows)
        try:
            from trader_shared.light_data import ensure_bars_ascending
        except ImportError:
            return list(rows)
        fixed, rewritten = ensure_bars_ascending(rows)
        if rewritten and fixed:
            _logger.info(
                "bars reordered ascending cache=%s target=%s n=%s",
                cache_key,
                target,
                len(fixed),
            )
            try:
                set_cached(
                    cache_key,
                    target,
                    {"fetch_date": today, "rows": fixed},
                )
            except OSError as exc:
                _logger.debug(
                    "get_day_scoped_bars rewrite failed %s/%s: %s",
                    cache_key,
                    target,
                    exc,
                )
        return fixed

    cached = get_cached(cache_key, target, ttl=TTL_BARS_DAY)
    if cached is not None:
        data = cached.data
        if is_fetch_date_today(data, today):
            rows = unwrap_bars_payload(data)
            if rows is not None and len(rows) >= min_rows:
                return _finalize(rows)
        # 旧格式：裸 list + 未过 TTL → 可先用，避免无意义回源
        if (
            isinstance(data, list)
            and len(data) >= min_rows
            and not cached.stale
        ):
            return _finalize(list(data))

    try:
        rows = fetch_fn() or []
    except Exception as exc:
        _logger.warning(
            "get_day_scoped_bars fetch failed %s/%s: %s", cache_key, target, exc
        )
        # 失败时只允许「同日」缓存；禁止跨日陈粮冒充 full
        if cached is not None:
            data = cached.data
            if is_fetch_date_today(data, today):
                hit = unwrap_bars_payload(data)
                if hit is not None and len(hit) >= min_rows:
                    return _finalize(hit)
            if (
                isinstance(data, list)
                and len(data) >= min_rows
                and not cached.stale
            ):
                return _finalize(list(data))
        return []

    if isinstance(rows, list) and len(rows) >= min_rows:
        fixed, _rewritten = (rows, False)
        try:
            from trader_shared.light_data import ensure_bars_ascending
            fixed, _rewritten = ensure_bars_ascending(rows)
        except ImportError:
            fixed = list(rows)
        try:
            set_cached(
                cache_key,
                target,
                {"fetch_date": today, "rows": fixed},
            )
        except OSError as exc:
            _logger.debug("get_day_scoped_bars write failed %s/%s: %s", cache_key, target, exc)
        return list(fixed) if isinstance(fixed, list) else []
    return list(rows) if isinstance(rows, list) else []


@dataclass
class CacheResult:
    """Cache wrapper supporting stale-while-revalidate."""
    data: Any
    stale: bool
    age_seconds: float
    source: str  # "memory" | "file"


def validate_bars(bars: list[dict]) -> bool:
    """Validate bar data before writing to cache.

    Checks:
    - Bar count >= 200 (enough history for MA250)
    - Each bar has close > 0
    - Dates are monotonically increasing
    """
    if not isinstance(bars, list) or len(bars) < 200:
        return False
    prev_date = ""
    for bar in bars:
        close = bar.get("close")
        if close is None or float(close) <= 0:
            return False
        date = str(bar.get("date") or bar.get("time") or "")
        if date and date < prev_date:
            return False
        if date:
            prev_date = date
    return True


_FLOCK_TIMEOUT = 5  # seconds to wait for file lock


def _acquire_lock(f, lock_type: int, timeout: float = _FLOCK_TIMEOUT) -> bool:
    """Acquire file lock with timeout. Returns True if acquired, False on timeout."""
    deadline = time.time() + timeout
    while True:
        try:
            fcntl.flock(f, lock_type | fcntl.LOCK_NB)
            return True
        except (OSError, BlockingIOError):
            if time.time() >= deadline:
                _logger.warning("File lock timeout after %.1fs", timeout)
                return False
            time.sleep(0.05)


def get_cached(key: str, target: str, ttl: int = TTL_DAILY) -> CacheResult | None:
    """Read cache if exists. Returns CacheResult with stale flag if expired, None if missing.

    Uses shared file lock (LOCK_SH) to prevent reading half-written files.
    """
    cache_file = CACHE_DIR / key / f"{target}.json"
    if not cache_file.exists():
        return None
    try:
        age = time.time() - cache_file.stat().st_mtime
        with open(cache_file, "r", encoding="utf-8") as f:
            if _acquire_lock(f, fcntl.LOCK_SH):
                try:
                    raw = f.read()
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
            else:
                raw = f.read()
        data = json.loads(raw)
        stale = age > ttl
        return CacheResult(data=data, stale=stale, age_seconds=round(age, 1), source="file")
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        _logger.debug("Cache read failed for %s/%s: %s", key, target, exc)
        return None


def get_cached_data(key: str, target: str, ttl: int = TTL_DAILY) -> Any | None:
    """Compatibility helper: returns cache data or None (ignores stale)."""
    result = get_cached(key, target, ttl)
    return result.data if result is not None else None


def set_cached(key: str, target: str, data: Any) -> None:
    """Write data to cache (atomic via temp file + rename, with exclusive file lock)."""
    cache_file = CACHE_DIR / key / f"{target}.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    # 临时文件名必须包含线程标识：同进程多线程 os.getpid() 相同，
    # 若只用 pid 会导致并发写同一 target 时 tmp 文件互相覆盖/丢失。
    tmp_file = cache_file.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp_file.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
        with open(cache_file, "a") as lock_f:
            if _acquire_lock(lock_f, fcntl.LOCK_EX):
                try:
                    tmp_file.replace(cache_file)
                finally:
                    fcntl.flock(lock_f, fcntl.LOCK_UN)
            else:
                # fix: lock timeout — skip write instead of racing without lock.
                # Cache miss is a performance issue, not a correctness issue; a racing
                # unlocked replace could overwrite another thread's newer write.
                _logger.warning("Cache write lock timeout for %s/%s, skipping write", key, target)
                tmp_file.unlink(missing_ok=True)
    except (OSError, TypeError) as exc:
        _logger.warning("Cache write failed for %s/%s: %s", key, target, exc)
        tmp_file.unlink(missing_ok=True)
        raise


def set_cached_validated(
    key: str,
    target: str,
    data: Any,
    validator: Callable[[Any], bool] | None = None,
) -> bool:
    """Write data to cache only if validation passes.

    Returns True if written, False if validation failed or write errored.
    """
    if validator is not None and not validator(data):
        return False
    try:
        set_cached(key, target, data)
        return True
    except (OSError, TypeError) as exc:
        _logger.debug("Validated cache write failed for %s/%s: %s", key, target, exc)
        return False


def invalidate(key: str, target: str) -> None:
    """Delete a specific cache entry."""
    cache_file = CACHE_DIR / key / f"{target}.json"
    cache_file.unlink(missing_ok=True)


def fetch_fund_flow_cached(symbol: str) -> dict[str, Any]:
    """获取资金流向数据（带缓存）。

    规则（用户约定）：
    - 同一自然日：第一次打网，之后直接读缓存
    - 换日：重新打网
    - 文件 TTL 仅作兜底，防止极旧文件

    返回 {"daily_flow": [...], "features": {...}, "fetch_date": "YYYY-MM-DD"} 或空 dict。
    """
    today = cache_calendar_date()
    # TTL 放宽到 3 天：真正是否可用看 fetch_date，避免「刚好 24h 跨日」误伤
    cached = get_cached(CACHE_FUND_FLOW, symbol, ttl=TTL_FUND_FLOW * 3)
    if cached is not None and is_fetch_date_today(cached.data, today):
        return cached.data
    try:
        from trader_shared.fund_flow_data import fetch_fund_flow, calc_fund_flow_features
        daily_flow = fetch_fund_flow(symbol)
        if not daily_flow:
            return {}
        features = calc_fund_flow_features(daily_flow)
        result = {
            "daily_flow": daily_flow,
            "features": features,
            "fetch_date": today,
        }
        set_cached(CACHE_FUND_FLOW, symbol, result)
        return result
    except (ImportError, OSError, ValueError) as exc:
        _logger.debug("Fund flow fetch/cache failed for %s: %s", symbol, exc)
        # 跨日 miss 但回源失败时：若有旧缓存且仅过了一天，仍返回旧数据并打标
        if cached is not None and isinstance(cached.data, dict) and cached.data.get("daily_flow"):
            out = dict(cached.data)
            out.setdefault("fetch_date", "stale")
            return out
        return {}


def cleanup_old_cache(max_age_days: int = 30) -> dict[str, int]:
    """Remove cache files older than max_age_days.

    Scans all subdirectories under CACHE_DIR and deletes .json files
    whose modification time is older than max_age_days.

    Args:
        max_age_days: Maximum age in days. Files older than this are deleted.

    Returns:
        Dict with 'scanned', 'deleted', 'failed' counts.
    """
    if not CACHE_DIR.exists():
        return {"scanned": 0, "deleted": 0, "failed": 0}

    cutoff_time = time.time() - (max_age_days * 86400)
    scanned = 0
    deleted = 0
    failed = 0

    for cache_file in CACHE_DIR.rglob("*.json"):
        scanned += 1
        try:
            if cache_file.stat().st_mtime < cutoff_time:
                cache_file.unlink()
                deleted += 1
                _logger.debug("Cleaned old cache file: %s", cache_file)
        except OSError as exc:
            failed += 1
            _logger.debug("Failed to clean cache file %s: %s", cache_file, exc)

    if deleted > 0:
        _logger.info("Cache cleanup: scanned=%d, deleted=%d, failed=%d", scanned, deleted, failed)

    return {"scanned": scanned, "deleted": deleted, "failed": failed}


def warm_chanlun_states() -> dict[str, Any]:
    """预建每只池内活跃票的 ``ChanlunEngine`` 状态到 ``CHANLUN_STATE_DIR/{code}.json``。

    供 T0 盯盘 / 次日分析 ``ChanlunEngine.load`` 直接复用，避免重复网络抓取 300 根历史。
    读取 ``~/.trader/pool.json`` 取 status 非「淘汰/已退出」的标的；对每个标的拉取日线
    （``include_5m/weekly/monthly/ticks=False``，暖缓存阶段已有 CACHE_DAILY，二次调用命中缓存极快），
    批量 build 引擎并 save。

    容错：单只构建/保存异常 → ``failed += 1`` + 记 ``errors``，**不阻断其他票 / 不阻断 warm**。

    Returns:
        {"total": int, "success": int, "failed": int, "errors": list[str]}
    """
    from pathlib import Path

    pool_path = Path.home() / ".trader" / "pool.json"
    if not pool_path.exists():
        return {"total": 0, "success": 0, "failed": 0, "errors": []}

    try:
        pool_data = json.loads(pool_path.read_text(encoding="utf-8"))
        items = pool_data.get("items", [])
        active_items = [
            item for item in items
            if item.get("status") not in ("淘汰", "已退出")
        ]
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        _logger.warning("warm_chanlun_states: failed to read pool.json: %s", exc)
        return {"total": 0, "success": 0, "failed": 0, "errors": [str(exc)]}

    if not active_items:
        return {"total": 0, "success": 0, "failed": 0, "errors": []}

    try:
        from trader_shared.data_provider import get_provider
        from trader_shared.config import LOOKBACK_DAYS, CHANLUN_STATE_DIR
        from trader_shared.chan_core import ChanlunEngine
    except ImportError as exc:
        return {
            "total": len(active_items), "success": 0, "failed": len(active_items),
            "errors": [f"import failed: {exc}"],
        }

    provider = get_provider()
    total = len(active_items)
    success = 0
    failed = 0
    errors: list[str] = []

    state_dir = Path(CHANLUN_STATE_DIR)
    state_dir.mkdir(parents=True, exist_ok=True)

    for item in active_items:
        name = item.get("name")
        if not name:
            failed += 1
            errors.append("item missing name")
            continue
        try:
            snapshot = provider.load_market_snapshot(
                name, days=LOOKBACK_DAYS,
                include_5m=False, include_weekly=False, include_monthly=False, include_ticks=False,
            )
            daily_bars = snapshot.daily_bars or []
            if not daily_bars:
                failed += 1
                errors.append(f"{name}: empty daily_bars")
                continue

            # 解析用于状态文件名的 code：snapshot 顶层 symbol/code → security.code → pool item code → name
            code = (
                getattr(snapshot, "code", None)
                or getattr(snapshot, "symbol", None)
                or getattr(getattr(snapshot, "security", None), "code", None)
                or item.get("code")
                or name
            )
            eng = ChanlunEngine()
            for b in daily_bars:
                eng.update_bar(b)
            eng.save(f"{CHANLUN_STATE_DIR}/{code}.json")
            success += 1
        except Exception as exc:  # 容错：绝不阻断其他票
            failed += 1
            errors.append(f"{name}: {exc}")

    return {"total": total, "success": success, "failed": failed, "errors": errors}


def warm_pool_cache() -> dict[str, Any]:
    """Pre-cache data for all active stocks in the pool.

    Called after market close (15:00) to prepare data for next day's analysis.
    Reads ~/.trader/pool.json and fetches full data for each active stock.

    Returns:
        {"total": int, "success": int, "failed": int, "skipped": int, "errors": list}
    """
    import sys
    from pathlib import Path

    pool_path = Path.home() / ".trader" / "pool.json"
    if not pool_path.exists():
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0, "errors": []}

    try:
        pool_data = json.loads(pool_path.read_text(encoding="utf-8"))
        items = pool_data.get("items", [])
        targets = [
            item["name"] for item in items
            if item.get("status") not in ("淘汰", "已退出")
        ]
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        _logger.warning("Failed to read pool.json: %s", exc)
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0, "errors": []}

    if not targets:
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0, "errors": []}

    try:
        from trader_shared.data_provider import get_provider
        from trader_shared.config import LOOKBACK_DAYS
    except ImportError:
        return {"total": len(targets), "success": 0, "failed": len(targets), "skipped": 0,
                "errors": ["data_provider or config not available"]}

    provider = get_provider()
    success = 0
    failed = 0
    errors: list[str] = []

    for name in targets:
        try:
            snapshot = provider.load_market_snapshot(name, days=LOOKBACK_DAYS, include_5m=False, include_weekly=False, include_monthly=False, include_ticks=False)
            if snapshot.daily_bars and snapshot.quote:
                success += 1
            else:
                failed += 1
                errors.append(f"{name}: incomplete data")
        except Exception as e:
            failed += 1
            errors.append(f"{name}: {e}")

    # Also warm market env cache
    try:
        from trader_shared.market_env import assess as _assess
        _assess()
    except (ImportError, OSError) as exc:
        _logger.debug("Market env cache warm failed: %s", exc)

    # Warm fund flow cache
    ff_success = 0
    ff_failed = 0
    for name in targets:
        try:
            result = fetch_fund_flow_cached(name)
            if result:
                ff_success += 1
            else:
                ff_failed += 1
        except Exception:
            ff_failed += 1

    # Clean up old cache files (older than 30 days)
    cleanup_result = cleanup_old_cache(max_age_days=30)

    # Phase 2 接入：预建池内活跃票的缠论增量引擎状态（容错，绝不阻断 warm）
    chanlun_result = warm_chanlun_states()

    return {
        "total": len(targets), "success": success, "failed": failed, "skipped": 0, "errors": errors,
        "fund_flow_success": ff_success, "fund_flow_failed": ff_failed,
        "cache_cleanup": cleanup_result,
        "chanlun": chanlun_result,
    }


def clear_cache(cache_type: str | None = None) -> int:
    """Clear cache files. If cache_type is specified, only clear that subdirectory.

    Returns number of files deleted.
    """
    if cache_type:
        target_dir = CACHE_DIR / cache_type
    else:
        target_dir = CACHE_DIR
    if not target_dir.exists():
        return 0
    count = 0
    for f in target_dir.rglob("*.json"):
        try:
            f.unlink()
            count += 1
        except OSError as exc:
            _logger.debug("Failed to delete cache file %s: %s", f, exc)
    return count


# ── Chunked cache reads for memory efficiency ────────────────────────


def get_cached_batches(
    key: str,
    target: str,
    ttl: int = TTL_DAILY,
    batch_size: int = 50,
) -> list[list[dict[str, Any]]] | None:
    """Read cached data and split into batches for memory-efficient processing.

    Instead of returning the entire cached list, this function splits it into
    batches of ``batch_size`` items. This is useful for processing large K-line
    datasets without loading everything into memory at once.

    Args:
        key: Cache subdirectory (e.g., CACHE_DAILY).
        target: Cache target identifier (e.g., stock code).
        ttl: Time-to-live in seconds.
        batch_size: Number of items per batch (default 50).

    Returns:
        List of batches, or None if cache miss.
    """
    result = get_cached(key, target, ttl)
    if result is None or not isinstance(result.data, list):
        return None

    data = result.data
    if not data:
        return []

    batches: list[list[dict[str, Any]]] = []
    for i in range(0, len(data), batch_size):
        batches.append(data[i : i + batch_size])
    return batches


def _normalize_bar_date(raw: Any) -> str:
    """统一为 YYYY-MM-DD；无法解析返回空串。"""
    s = str(raw or "").strip()
    if not s:
        return ""
    # YYYYMMDD
    if len(s) >= 8 and s[:8].isdigit() and "-" not in s[:10]:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    # YYYY-MM-DD...
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return s[:10] if len(s) >= 10 else s


def merge_daily_bars_with_quote(
    cached_bars: list[dict],
    quote: dict[str, Any],
) -> list[dict]:
    """Merge cached historical daily bars with session quote into one partial daily bar.

    注意：主分析路径（report_builder / load_market_snapshot）默认 **不** 调用本函数，
    以免 partial 今日 K 污染策略。仅供缓存预热/显式需要「日K含今日」的调用方。

    Strategy:
    - 交易日优先 quote.trade_date，否则日历 today
    - bar 日期统一 YYYY-MM-DD 再比较，避免重复「今日」
    """
    if not cached_bars or not quote:
        return cached_bars

    session_str = _normalize_bar_date(quote.get("trade_date")) or datetime.now().strftime("%Y-%m-%d")

    def _to_float(v: Any) -> float | None:
        if v in (None, "", "-", "--"):
            return None
        try:
            return float(str(v).replace(",", ""))
        except (ValueError, TypeError):
            return None

    current_price = _to_float(quote.get("current_price"))
    if current_price is None:
        return cached_bars

    today_bar = {
        "date": session_str,
        "time": session_str,
        "open": _to_float(quote.get("open")) or current_price,
        "high": _to_float(quote.get("high")) or current_price,
        "low": _to_float(quote.get("low")) or current_price,
        "close": current_price,
        "volume": _to_float(quote.get("volume")),
        "amount": _to_float(quote.get("amount")),
        "data_source": "realtime-merge",
        "data_status": "partial",
    }

    # Copy ATR fields from the last cached bar (ATR is a slow variable, previous day's value is a good approximation)
    if cached_bars:
        # 取日期最新一根，勿假定列表已正序
        def _bar_d(b: dict) -> str:
            return _normalize_bar_date(b.get("date") or b.get("time") or b.get("trade_date") or "") or ""

        prev_bar = max(cached_bars, key=_bar_d)
        for atr_key in ("atr14", "atr_ratio", "atr7", "tr"):
            if prev_bar.get(atr_key) is not None:
                today_bar[atr_key] = prev_bar[atr_key]

    # Check if session day already exists in cached bars
    result = []
    today_replaced = False
    for bar in cached_bars:
        bar_date = _normalize_bar_date(bar.get("date") or bar.get("time") or "")
        if bar_date and bar_date == session_str:
            result.append(today_bar)
            today_replaced = True
        else:
            result.append(bar)

    if not today_replaced:
        result.append(today_bar)

    # 统一日期为 YYYY-MM-DD，再正序（避免 20260725 与 2026-07-28 字典序错乱）
    for bar in result:
        if not isinstance(bar, dict):
            continue
        nd = _normalize_bar_date(bar.get("date") or bar.get("time") or bar.get("trade_date") or "")
        if nd:
            bar["date"] = nd

    # 合并后强制正序（输入可能倒序）；ATR 按正序重算
    try:
        from trader_shared.light_data import ensure_bars_ascending
        fixed, _ = ensure_bars_ascending(result)
        return fixed
    except ImportError:
        result.sort(
            key=lambda b: _normalize_bar_date(
                b.get("date") or b.get("time") or b.get("trade_date") or ""
            )
            or ""
        )
        return result


# ── 内存缓存：merge_daily_bars_with_quote ──────────────────────
# 同一天对同一标的重复调用此函数（如 cmd_refresh 全池刷新）时，
# cached_bars 和 quote 不变，直接返回缓存结果。

_merge_daily_cache: dict[tuple, list[dict]] = {}
_merge_daily_lock = threading.Lock()
_MERGE_CACHE_MAX = 256


def merge_daily_bars_cached(
    cached_bars: list[dict],
    quote: dict[str, Any],
) -> list[dict]:
    """带进程内 LRU 缓存的 daily bars 合并。

    缓存键由 bars 日期序列 + quote 的 (trade_date, current_price, volume) 组成。
    多线程安全：读写加锁。
    返回值始终是浅拷贝，不会污染缓存。
    """
    # 构建可哈希的缓存键
    dates = tuple(str(b.get("date") or b.get("time") or b.get("trade_date") or "") for b in cached_bars)
    quote_key = (
        str(quote.get("trade_date") or ""),
        str(quote.get("current_price") or 0),
        str(quote.get("volume") or 0),
    )
    key = (dates, quote_key)

    with _merge_daily_lock:
        cached = _merge_daily_cache.get(key)
        if cached is not None:
            return list(cached)

    # Cache miss → 调用原函数
    result = merge_daily_bars_with_quote(cached_bars, quote)

    with _merge_daily_lock:
        if len(_merge_daily_cache) >= _MERGE_CACHE_MAX:
            # FIFO 淘汰单个最早条目（而非一次清空一半）
            _merge_daily_cache.pop(next(iter(_merge_daily_cache)))
        _merge_daily_cache[key] = list(result)

    return list(result)
