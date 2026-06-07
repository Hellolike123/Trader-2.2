# PRD: 修复 review/t0/win-rate/data-layer 主流程 2 P0 + 6 P1 准确性 Bug

## 背景

最新 commit (7b7784f) "refactor(review): optimize output format - 14 sections to 9 sections" 引入了一个 **P0 阻塞性 bug**，导致 `review script --target` 盘后复盘、午间复盘、多股对比、持仓轮动全部崩溃。同时 4 个 P1 准确性 bug 影响 T0 信号胜率回测与缓存一致性。

第二轮数据层扫描（3 Agent 独立验证）新发现 **1 个 P0**（akshare 后端完全崩溃）+ **3 个 P1**（HMM 静默降级、限速器 I/O 等）。

经过 3 个 Agent（A 检查、B 交叉验证、C 裁决）的独立验证，下列 8 个问题已确认且证据链完整。

## 修复目标

修复 2 个 P0 阻塞 bug + 6 个 P1 准确性 bug，让 review 主流程恢复、T0 胜率回测能拿到真实盘中数据、akshare 后端可用、HMM 降级可观测、限速器无磁盘 I/O 开销。

## 修复清单

### P0 #1: `review_core.py` 变量顺序导致 `UnboundLocalError`

**文件**：`01-功能包-packages/review/scripts/review_core.py`

**当前问题**：
- `build_review()` 函数内 `selected_date` 在 line 562 才被赋值
- 但在 lines 548, 552, 563, 578, 603, 630 都被使用
- Python 编译期一旦看到函数内存在对 `selected_date` 的赋值，整个函数体内该名称视为 local
- 第一次使用 (line 548) 触发 `UnboundLocalError: cannot access local variable 'selected_date' where it is not associated with a value`

**影响范围**：
- `review script --target <NAME>` 盘后复盘
- `review script --session midday` 午间复盘
- `review script --compare A B` 多股对比
- `review script --portfolio` 持仓轮动

**为什么测试没发现**：
- `test_review_contract.py` 只测 `render_single(sample_review())`，不触发 `build_review()` 完整路径
- 67 个 review 测试全部是 schema/contract 校验，未真实调用 `build_review()`

**修复方案**：
把 `selected_date = trade_date or (daily[-1].get("date") if daily else None) or quote.get("trade_date")` 这行（line 562）上移到 try 块之前（line 543 之前），确保所有使用都发生在赋值之后。

**验证方法**：
```python
mod = importlib.import_module("01-功能包-packages.review.scripts.review_core")
mod.build_review("000001", cost=None, trade_date="2026-06-06", session="close")
```
不应抛出 UnboundLocalError。

---

### P1 #2: win-rate 时间过滤器误杀 T0 盘中信号

**文件**：
- `01-功能包-packages/trader/scripts/run_analysis.py:910-913`
- `01-功能包-packages/trader/scripts/new_render.py:44-47`（孤儿，参见 #5）
- `01-功能包-packages/review/scripts/review_render.py:95-98`

**当前问题**：
```python
time_part = analysis_time[11:].strip() if len(analysis_time) >= 16 else ""
if not (time_part >= "15:00"):
    continue
```
T0 信号在盘中生成（`analysis_time` 形如 `"2026-06-06 10:35:22"`），`time_part="10:35"` < `"15:00"` 被 `continue` 跳过。盘后 15:30+ 的 `review_result` 才能进入胜率分桶，T0 盘中数据全部被误杀。

**测试盲区**：
`test_contract.py:558` 用 `analysis_time="2026-01-09 15:30:00"` 模拟 T0 信号，与生产不符。

**修复方案**：
时间过滤只对 `review_result` 生效（review 信号才有 15:00 之后的 `analysis_time`）。修改为：
```python
sig_type = sig.get("signal_type")
if sig_type == "review_result":
    time_part = str(sig.get("analysis_time") or "")[11:].strip()
    if len(time_part) < 5 or not (time_part >= "15:00"):
        continue
```
`low_buy_triggered` 等 T0 信号不再被时间过滤，胜率回测能拿到真实盘中数据。

**注意**：必须 3 个副本同步修改。

---

### P1 #3: T0 卖信号 `direction="neutral"` + `signal_type` 白名单双盲

**文件 A**：`01-功能包-packages/t0/scripts/t0_core.py:135`

**当前问题**：
```python
direction = "bullish_lean" if side == "buy" else "neutral"
```
T0 卖信号硬编码 `direction="neutral"`，win-rate 桶（`run_analysis.py:933,935`）只匹配 `("bullish", "bullish_lean", "bearish", "bearish_lean")`，neutral 永不命中。

**文件 B**：`01-功能包-packages/trader/scripts/run_analysis.py:907`（白名单）

**当前问题**：
```python
if sig.get("signal_type") not in ("review_result", "low_buy_triggered"):
    continue
```
T0 卖信号的 `signal_type == "high_sell_triggered"`（见 `t0_core.py:358`）在循环外就被剔除，根本走不到 `direction` 判断。

**双盲症状**：T0 卖方向在胜率回测中 0 计数，影响信号追踪 + 仓位轮动决策。

**修复方案**（任选其一）：
1. 修 `t0_core.py:135`：`direction = "bearish_lean" if side == "sell" else "bullish_lean"`，并把 `"high_sell_triggered"` 加进 `run_analysis.py:907` 的白名单
2. 修 `run_analysis.py:907`：白名单改为 `("review_result", "low_buy_triggered", "high_sell_triggered")`

**推荐方案 1**（更彻底）。

---

### P1 #4: `t0_run.py:101` 漏传 `trade_date`

**文件**：`01-功能包-packages/t0/scripts/t0_run.py:99-101`

**当前问题**：
```python
ticks = provider.fetch_ticks(sec, count=500)
report_data["tick_data"] = ticks
save_tick_cache(sec.ts_code, ticks)  # ← 缺 trade_date
```
`tick_cache.py:21` 签名是 `save_tick_cache(symbol, tick_data, trade_date=None)`，缺省回退到 `date.today()`。

对比 `review_core.py:548`：
```python
save_tick_cache(sec.ts_code, ticks, trade_date=selected_date)  # 传了
```

**跨日问题**：
- t0 盘中写入：`date.today()` 键（"今天"）
- 盘后凌晨跑 review：`selected_date` 是复盘日（"昨天"）
- 跨日命中失败，`load_tick_cache` 永远拿不到 t0 当天抓的 tick

**修复方案**：
```python
save_tick_cache(sec.ts_code, ticks, trade_date=quote.get("trade_date"))
```
让 t0 和 review 行为一致。

---

### P1 #5: 午间复盘合同违例 — `review_label` 死代码

**文件**：`01-功能包-packages/review/scripts/review_render.py:246, 260`

**当前问题**：
- Line 246: `review_label = "午间复盘" if is_midday else "盘后复盘"` — 变量算了但从未读取
- Line 260 硬编码：`lines.append(f"盘后复盘 — {name}（{code}）")`
- 即使 `is_midday=True`，首行仍是"盘后复盘 —"，违反 `review_output-contract.md:8,83` 合同要求

**修复方案**：
将 line 260 改为：
```python
session_label = "午间复盘" if is_midday else "盘后复盘"
lines.append(f"{session_label} — {name}（{code}）")
```
并删除 line 246 的 `review_label = ...`（替换为 `session_label`）。

---

### P0 #2: `data_provider.py:361` akshare 后端 `to_float` NameError

**文件**：`02-共享模块-shared/trader_shared/data_provider.py:361, 387`

**当前问题**：
- `_akshare_to_bar` (line 360) 和 `_akshare_fetch_quote` (line 387) 直接调用 `to_float(...)` 作为 bare function
- 模块顶部（lines 15-25）没有 import `to_float`
- 唯一可用的 `to_float` 是 `self.to_float()`（line 263 的实例方法），但这两个函数是 instance method 之外定义的 helper，没有 `self`
- 当 `TRADER_DATA_PROVIDER=akshare` 时立即抛 `NameError: name 'to_float' is not defined`
- 3 个 Agent A/B/C 一致确认

**影响范围**：
- akshare 后端**完全不可用**
- 任何配置 `data_provider=akshare` 的用户（macOS/Linux 几乎所有使用 fallback 的用户）都会崩溃
- 当前默认是 tencent，但 akshare 是主要 fallback

**修复方案**：
在 `data_provider.py` 顶部增加 import：
```python
from trader_shared.light_data import to_float
```
注意：`light_data.to_float` 已是项目内导出的工具函数（`light_data.py:1074`），无循环依赖风险。

**验证方法**：
```python
import os
os.environ["TRADER_DATA_PROVIDER"] = "akshare"
from trader_shared.data_provider import get_provider
p = get_provider()
sec = p.resolve_security("000001")
bars = p.fetch_qfq_daily(sec, days=30)  # 不应抛 NameError
```

---

### P1 #6: `market_env.py` HMM 异常静默吞掉

**文件**：`02-共享模块-shared/scripts/market_env.py:176-187`

**当前问题**：
- Line 180: `index_returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]` — `closes[i-1] == 0` 时（垃圾数据）触发 `ZeroDivisionError`
- Line 187: `except Exception: pass` bare except 吞掉所有 HMM 错误，fallback 到 `hmm_regime_en="range"`
- 用户完全不知道 regime 检测失败/降级，做出的仓位决策基于错误信号
- 3 个 Agent A/B/C 一致确认（同根问题合并修复）

**修复方案**：
```python
except Exception as exc:
    _logger.debug("HMM regime detection failed: %s", exc)
```
其中 `_logger` 用现有 `from trader_shared._logging import get_logger` 即可。

---

### P1 #7: `light_data.py` 限速器每次 API 调用都读写文件

**文件**：`02-共享模块-shared/trader_shared/light_data.py:196-214`（`APIRequestRateLimiter.check_and_record`）

**当前问题**：
- 每次调用都 `_load()` (line 199) → JSON 反序列化 → 过滤 → `_save()` (line 213) → JSON 序列化写盘
- 单股分析调用 `fetch_qfq_daily` + `fetch_quote` + `fetch_kline` 约 3-5 次/股，15-30ms 不必要磁盘 I/O
- 选股池批量分析时 N 票 × 5 调用 = 5N 次文件 I/O，延迟累积明显
- 3 个 Agent A/B/C 一致确认

**修复方案**：
将 `_load()` 改为内存缓存 + 定期落盘：
```python
class APIRequestRateLimiter:
    def __init__(self, ...) -> None:
        ...
        self._cache: dict | None = None  # 内存缓存
        self._dirty = False
    
    def _get_data(self) -> dict:
        """Lazy load + cache. Reload from disk only on first call or after explicit invalidate."""
        if self._cache is None:
            self._cache = self._load_from_disk()
        return self._cache
    
    def check_and_record(self, ...) -> bool:
        now = time.time()
        data = self._get_data()
        calls = [...]  # 同现有过滤逻辑
        if len(min_calls) >= max_per_min or len(calls) >= max_per_hour:
            return False
        calls.append(now)
        data["calls"] = calls
        self._dirty = True
        # 仅在 dirty 状态下写盘，或每 N 次写一次
        return True
    
    def _flush(self) -> None:
        """Explicit flush; called by atexit or every N writes."""
        if self._dirty and self._cache is not None:
            self._save(self._cache)
            self._dirty = False
```
注册 `atexit.register(self._flush)` 在模块加载时保证进程退出前落盘。

**验证方法**：
```python
import time
r = APIRequestRateLimiter(limit_file="/tmp/test_rl.json")
t0 = time.perf_counter()
for _ in range(100):
    r.check_and_record()  # 内存操作，应 < 1ms/次
assert (time.perf_counter() - t0) < 0.1  # 100 次 < 100ms
```

---

## 验收标准

### 必须通过
- 所有现有测试通过：`pytest 02-共享模块-shared/tests/ 01-功能包-packages/*/tests/`
- 新增回归测试：
  1. `test_review_core.py::test_build_review_does_not_raise` — 真实调用 `build_review()` 验证不抛 UnboundLocalError
  2. `test_win_rate_t0_intraday.py::test_low_buy_triggered_intraday_included` — 用 `analysis_time="2026-06-06 10:35:00"` 的 T0 信号验证能进入胜率分桶
  3. `test_t0_direction.py::test_high_sell_triggered_bearish_lean` — 验证 T0 卖信号 `direction="bearish_lean"`
  4. `test_tick_cache.py::test_save_load_with_trade_date` — 验证 `save_tick_cache` 传 `trade_date` 后跨日不丢
  5. `test_data_provider.py::test_akshare_to_float_imported` — 设置 `TRADER_DATA_PROVIDER=akshare` 后 `fetch_qfq_daily` 不抛 NameError
  6. `test_market_env.py::test_hmm_failure_logs` — 注入 HMM 异常，验证日志记录且 fallback 仍工作
  7. `test_rate_limiter.py::test_in_memory_cache` — 100 次连续 `check_and_record()` 总耗时 < 100ms

### 手动验证
- `python3 01-功能包-packages/review/scripts/review_core.py` 调用 `build_review()` 不报错
- `python3 01-功能包-packages/t0/scripts/t0_run.py` 盘后跑一遍，能正确写入并读取 tick cache
- `TRADER_DATA_PROVIDER=akshare python3 -c "from trader_shared.data_provider import get_provider; p = get_provider(); print(p.fetch_qfq_daily(p.resolve_security('000001'), days=30).head())"` 不抛 NameError

---

## 范围之外

**不在本次修复范围**（P2/P3 项目，单独 issue 跟踪）：

- P2 #8: `_load_historical_win_rate` 三份复制粘贴 — 删除孤儿 `new_render.py` 或下沉到 `trader_shared/`
- P2 #9: chip_migration 字段形状漂移（`support_diff` vs `support_migration`）
- P2 #10: 偏多/警惕 节有意删除但文档没说明
- P3 #11: `t0_core.py:286` `enumerate(exit_items, 1)` 起始参数丢弃
- P2 数据层：tick_cache 非原子写、market_env 除零、单例线程锁、fcntl Unix-only、重复 import、sanitize_quote 边界

**先前发现的准确性 bug**（需要单独建任务）：
- 阶段状态没按股票隔离
- 评分 gap 逻辑矛盾
- 威科夫无信号当看多
- 浮亏一刀切禁止加仓
- 池子不检测停牌
- 融合层冲突消解静默归零动量
- import 路径错误配置不生效
- 阶段锁定按调用次数递减

---

## 实施注意事项

1. **三份 _load_historical_win_rate 副本**：修复 #2 时必须 3 个副本（`run_analysis.py:867`、`new_render.py:1`、`review_render.py:59`）同步修改
2. **不修改契约文档**：修复后输出与 9 段式 contract 完全一致，无需改 `review_output-contract.md`
3. **不引入新依赖**：纯代码修复
4. **测试必须真实触发 build_review**：现有 schema 测试无法捕获 #1，必须加完整路径回归测试
5. **P0 #2 修复需谨慎 import 顺序**：`data_provider.py` 已有 `light_data` 的 lazy import（`from trader_shared.light_data import to_float as _fn`），顶层直接 import 应无循环依赖，但需先确认 `light_data.__init__` 不会导入 `data_provider`
6. **P1 #7 限速器 atexit 注册**：`atexit.register` 在 import 时执行，确保只注册一次（用模块级单例 `_API_RATE_LIMITER`）

---

## 风险评估

- **P0 #1 修复**：低风险，纯代码顺序调整，1 行
- **P1 #2 修复**：低风险，加 `if sig_type == "review_result"` 守卫
- **P1 #3 修复**：低风险，改一个常量 + 改一个白名单
- **P1 #4 修复**：低风险，加一个参数
- **P1 #5 修复**：低风险，变量重命名
- **P0 #2 修复**：低风险，新增 1 行 import；但需先验证 akshare 端到端能跑通（测试覆盖）
- **P1 #6 修复**：低风险，bare except 改 logger.debug；行为不变仅可观测
- **P1 #7 修复**：中等风险，限速器从"每次写盘"改为"内存+flush"，需保证进程崩溃时**最多丢失最新 1 次请求记录**（可接受，因限速是 best-effort）

总变更预估：25-40 行代码 + 7 个测试
