## 1. 严重修复

- [x] 1.1 `fund_flow_data.py` — 将 `import requests` 和 `requests.get()` 改为 `urllib.request` + `json.loads()`，删除 `requests` 导入
- [x] 1.2 `main_force.py:_result()` — 返回值增加 `daily_flow_5d` 字段，值为 `features.get("daily_flow_5d", [])`

## 2. 中等修复

- [x] 2.1 `main_force.py:99-103` — 将 `len(bars) >= 3` 改为 `len(bars) >= 4`（因为 line 102 访问 `bars[-4]`）
- [x] 2.2 `main_force.py:60` — 删除 `daily_5d = features.get("daily_flow_5d", [])` 这行（未使用的死代码）
- [x] 2.3 `main_force.py:119` — 将 `if daily_5d[-1] < 0:` 改为 `if daily_5d[-1] > 0:`（资金回流应该是正值）

## 3. 验证

- [x] 3.1 跑测试确认无回归：`python3 -m pytest 02-共享模块-shared/tests/test_main_force.py -v`（23 passed）
- [x] 3.2 跑全量测试：`python3 -m pytest 02-共享模块-shared/tests/ -q`（593 passed）
