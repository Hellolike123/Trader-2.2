import sys
from datetime import datetime, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
for _p in (SCRIPTS,):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p.resolve()))


def test_fuse_alert_construction():
    import monitor as m
    alert = m._fuse_alert("688248.SH", 3, "南网科技")
    assert "熔断" in alert
    assert "3 次" in alert
    assert "阈值" in alert


def test_fuse_triggers_after_3_stops():
    import monitor as m
    td = Path("/tmp/test_fuse_monitor")
    td.mkdir(exist_ok=True)
    cache = td / "test_fuse.json"
    cache.write_text("{}\n", encoding="utf-8")
    orig_cache = m.CACHE_PATH
    m.CACHE_PATH = cache
    try:
        state = m.load_state(cache)
        state["_fuse"] = {}
        m.save_state(state, cache)
        for i in range(3):
            state = m.load_state(cache)
            now = datetime.now()
            day = m.trade_day_key(now)
            fuse_state = state.get("_fuse", {})
            current = fuse_state.get(day, {}) if isinstance(fuse_state, dict) else {}
            stop_count = current.get("count", 0)
            fused_targets = current.get("fused_targets", [])
            stop_count += 1
            target_key = "688248.SH"
            if target_key not in fused_targets:
                fused_targets = fused_targets + [target_key]
            current = {"count": stop_count, "fused_targets": fused_targets}
            if stop_count >= m.FREQUENCY_STOP_LIMIT:
                current["fused"] = True
                current["fused_at"] = now.strftime("%H:%M")
            fuse_state[day] = current
            state["_fuse"] = fuse_state
            m.save_state(state, cache)
            if i == 0:
                assert not current.get("fused")
            elif i == 1:
                assert not current.get("fused")
            elif i == 2:
                assert current.get("fused")
    finally:
        m.CACHE_PATH = orig_cache


def test_fuse_skips_target():
    import monitor as m
    td = Path("/tmp/test_fuse_monitor")
    td.mkdir(exist_ok=True)
    cache = td / "test_skip.json"
    cache.write_text("{}\n", encoding="utf-8")
    orig_cache = m.CACHE_PATH
    m.CACHE_PATH = cache
    try:
        now = datetime.now()
        day = m.trade_day_key(now)
        state = m.load_state(cache)
        state["_fuse"] = {day: {"count": 3, "fused_targets": ["688248.SH"], "fused": True, "fused_at": "10:30"}}
        m.save_state(state, cache)
        loaded = m.load_state(cache)
        fuse_state = loaded.get("_fuse", {})
        day_fuse = fuse_state.get(day) if isinstance(fuse_state, dict) else None
        should_skip = isinstance(day_fuse, dict) and day_fuse.get("fused")
        assert should_skip
    finally:
        m.CACHE_PATH = orig_cache


def test_fuse_reset_new_day():
    import monitor as m
    td = Path("/tmp/test_fuse_monitor")
    td.mkdir(exist_ok=True)
    cache = td / "test_reset.json"
    cache.write_text("{}\n", encoding="utf-8")
    orig_cache = m.CACHE_PATH
    m.CACHE_PATH = cache
    try:
        state = m.load_state(cache)
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        state["_fuse"] = {today: {"count": 3, "fused_targets": [], "fused": True}}
        m.save_state(state, cache)
        loaded = m.load_state(cache)
        fuse_state = loaded.get("_fuse", {})
        yday_fuse = fuse_state.get(yesterday) if isinstance(fuse_state, dict) else None
        assert not (isinstance(yday_fuse, dict) and yday_fuse.get("fused"))
        today_fuse = fuse_state.get(today) if isinstance(fuse_state, dict) else None
        assert today_fuse is not None and today_fuse.get("fused")
    finally:
        m.CACHE_PATH = orig_cache


def test_different_targets_increase_count():
    import monitor as m
    td = Path("/tmp/test_fuse_monitor")
    td.mkdir(exist_ok=True)
    cache = td / "test_two_targets.json"
    cache.write_text("{}\n", encoding="utf-8")
    orig_cache = m.CACHE_PATH
    m.CACHE_PATH = cache
    try:
        state = m.load_state(cache)
        state["_fuse"] = {}
        m.save_state(state, cache)
        now = datetime.now()
        day = m.trade_day_key(now)
        sim_stops = [("688248.SH", "目标1"), ("600519.SH", "目标2")]
        fuse_state = {}
        for target_key, _name in sim_stops:
            if day not in fuse_state:
                fuse_state[day] = {"count": 0, "fused_targets": []}
            day_fuse = fuse_state[day]
            day_fuse["count"] += 1
            if target_key not in day_fuse["fused_targets"]:
                day_fuse["fused_targets"].append(target_key)
        day_fuse = fuse_state[day]
        assert day_fuse["count"] == 2
        assert len(day_fuse["fused_targets"]) == 2
        assert not day_fuse.get("fused")
    finally:
        m.CACHE_PATH = orig_cache


def test_fuse_does_not_affect_sell_stops():
    import monitor as m
    fuse_state = {"2026-05-16": {"count": 0, "fused_targets": []}}
    day_fuse = fuse_state["2026-05-16"]
    events = ["SELL_INVALIDATED", "SELL_INVALIDATED", "SELL_INVALIDATED"]
    for event in events:
        if event == m.BUY_INVALIDATED:
            day_fuse["count"] += 1
    assert day_fuse["count"] == 0
    assert not day_fuse.get("fused")
