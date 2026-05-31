## 1. 严重崩溃修复

- [x] 1.1 `market_env.py:72` — 在 `if price_part:` 前加 `current = 0` 初始化
- [x] 1.2 `t0_candidate_core.py:171` — 在 fallback 分支前定义 `_FUSION_STATUS_MAP: dict[str, str] = {}`
- [x] 1.3 `structure_core.py:304/319/332` — 将 `float(dict.get("confidence", 0))` 改为 `float(dict.get("confidence") or 0)`
- [x] 1.4 `self_calibration.py:120` — 收益率计算加 `if slice_closes[i-1] != 0` 过滤

## 2. 中等逻辑错误修复

- [x] 2.1 `decision_core.py` — `status_layers()` 增加 `vp_result=None` 参数，透传到 `_check_theory_breakout()`
- [x] 2.2 `structure_core.py:364-365` — `choose_level()` 调用前检查 support_levels/resistance_levels 是否为空
- [x] 2.3 `self_calibration.py:77` — 将 `r.get("return_pct", r.get("pnl_pct", 0.0)) or 0.0` 改为先检查 None 再回退 pnl_pct
- [x] 2.4 `monitor.py:393-394` — 将 `plan.get("buy", {})` 改为 `plan.get("buy") or {}`
- [x] 2.5 `market_env.py:222-223` — 将 `if ma5` 改为 `if ma5 is not None`
- [x] 2.6 `decision_core.py:269` — 将 `ma_values.get("ma5") or float("inf")` 改为 None-safe 写法

## 3. 防御性缺陷修复

- [x] 3.1 `market_env.py` — 移除未使用的导入：`sys`, `Path`, `normalize_bars`, `import trader_shared`
- [x] 3.2 `price_point_engine.py:296` — 将 `max(bb.keys(), default=-1)` 改为 `max(bb.keys()) if bb else {}` 模式
- [x] 3.3 `decision_core.py:448` — 将 `str(item.get("status"))` 改为 `item.get("status") or ""`
- [x] 3.4 `self_calibration.py:86` — 日期集合过滤 None：`if "trade_date" in sig and sig["trade_date"] is not None`
- [x] 3.5 `self_calibration.py:108` — 将 `float(b["close"])` 改为 `to_float(b.get("close"))`
- [x] 3.6 `self_calibration.py:109` — 将 `b["date"]` 改为 `b.get("date", "")`
- [x] 3.7 `structure_core.py:227-262` — 删除重复的 regime 计算（保留第一处）
- [x] 3.8 `big_order.py:162` — 列表推导中 to_float 用 walrus 避免重复调用
- [x] 3.9 `structure_core.py:456` — 同上，to_float 用 walrus 避免重复调用
