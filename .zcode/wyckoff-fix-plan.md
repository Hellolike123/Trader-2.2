# Wyckoff 经典信号 Bug 修复计划

基于三 Agent 审查报告，以下为需修复的问题及具体修改方案。

---

## P0 — 功能 Bug（必须修）

### Fix 1: `_detect_lps` None 数据误触发

**文件**: `02-共享模块-shared/trader_shared/wyckoff_core.py:616-618`

**问题**: `_detect_lps` 对 pullback 的 OHLCV 用 `to_float(...) or 0` fallback，当 bar 字段为 None 时静默变成 0.0，缺失数据的 bar 可能被误判为"缩量/下行"从而错误触发 LPS。其他检测函数（如 `_detect_spring`）对 None 做了显式 `continue` 跳过。

**修复方案**: 在 `_detect_lps` 的 pullback 遍历循环中，将 `to_float(x) or 0` 改为先检查 None，若为 None 则 `continue` 跳过该 bar。与 `_detect_spring` 保持一致的 None 处理模式。

**参考实现**（伪代码）:
```python
# 现在
close = to_float(bar.get("close")) or 0
# 改为
close = to_float(bar.get("close"))
if close is None:
    continue
```

对 pullback 循环中的 open/high/low/close/volume 全部做同样处理。

---

### Fix 2: fallback 阈值漂移

**文件**: `02-共享模块-shared/trader_shared/wyckoff_core.py:43`

**问题**: fallback 中 `WYCKOFF_BC_VOL_RATIO_THRESHOLD = 1.5`，但 `config.py:94` 中为 `1.8`。config 导入失败时 BC 检测阈值从 1.8 降到 1.5，导致更多 bar 被误判为 BC，可能误触发 AR 信号。

**修复方案**: 将 fallback 值从 `1.5` 改为 `1.8`，与 config.py 保持一致。在 fallback 块中加注释标注 `# must match config.py:94`。

---

## P1 — 测试覆盖不足

### Fix 3: `TestWyckoffToSignal` 缺少新信号测试

**文件**: `02-共享模块-shared/tests/test_fusion_core.py:203-257`

**问题**: `TestWyckoffToSignal` 仅测试 Spring/Upthrust/divergence/no_signal，未测试 AR/SOS/ST/LPS 被 `_wyckoff_to_signal` 消费的路径。

**修复方案**: 新增 4 个测试方法：
- `test_ar_signal_mapping`: 构造 ar=True 的 signals_detail，验证 direction=1, confidence=0.6
- `test_sos_signal_mapping`: 构造 sos=True 的 signals_detail，验证 direction=1, confidence=0.7
- `test_st_signal_mapping`: 构造 st=True 的 signals_detail，验证 direction=-1, confidence=0.5
- `test_lps_signal_mapping`: 构造 lps=True 的 signals_detail，验证 direction=-1, confidence=0.5

每个测试构造最小化的 signals_detail dict，验证 `_wyckoff_to_signal` 的输出 direction 和 confidence。

---

### Fix 4: `TestWyckoffScoreWithClassicSignals` 未验证精确分数贡献

**文件**: `02-共享模块-shared/tests/test_wyckoff_core.py:639-676`

**问题**: 现有 3 个测试仅 assert 不崩溃，未验证 AR(+10)/SOS(+15)/ST(+8)/LPS(+12) 各自对 raw_score 的精确贡献。

**修复方案**: 补充 4 个独立测试，每个测试只触发一个新信号，验证 raw_score 增量：
- `test_ar_adds_10`: 只触发 AR，assert raw_score 增加 10
- `test_sos_adds_15`: 只触发 SOS，assert raw_score 增加 15
- `test_st_adds_8`: 只触发 ST，assert raw_score 增加 8
- `test_lps_adds_12`: 只触发 LPS，assert raw_score 增加 12

同时补充 ST 用例从 3 个到 4 个（spec 要求 ≥4）。

---

### Fix 5: `wyckoff_score_to_direction` 死代码

**文件**: `02-共享模块-shared/trader_shared/fusion_core.py:359-389`

**问题**: `wyckoff_score_to_direction` 已实现但无任何生产调用方，仅在测试中被引用。

**修复方案**: 二选一：
- **选项 A（推荐）**: 在 `merge_decisions` 中接入，当 fusion 置信度不足时 fallback 到 score-based direction
- **选项 B**: 删除该函数及其测试，保持当前 `_wyckoff_to_signal` 直接映射逻辑

---

## P2 — 文档/注释（可选修）

### Fix 6: docstring 威科夫阶段顺序错误

**文件**: `02-共享模块-shared/trader_shared/wyckoff_core.py:563`

**问题**: `_detect_lps` docstring 写 "→ 回调 (LPS) → SOS → 主升"，正确应为 "→ SOS → 回调 → LPS"。

**修复方案**: 修正 docstring 文字顺序。

---

### Fix 7: spec 注释 math 错误 + "不改"承诺过时

**文件**: `01-功能包-packages/trader/specs/spec-wyckoff-classic-signals.md:130, 146-149`

**问题**: 注释 `max(85, 55) * 1.1 ≈ 95` 实际 85×1.1=93.5；声明下游"不改"但实际改了。

**修复方案**: 修正注释数值，更新下游描述为"已更新以消费新字段"。

---

## 执行顺序建议

```
Fix 1 (P0) → Fix 2 (P0) → Fix 3 (P1) → Fix 4 (P1) → Fix 5 (P1) → Fix 6-7 (P2)
```

P0 修完跑一次全量测试确认无回归，再做 P1。

## 验证命令

```bash
python3 -m pytest 02-共享模块-shared/tests/test_wyckoff_core.py -v
python3 -m pytest 02-共享模块-shared/tests/test_fusion_core.py -v
python3 -m pytest 02-共享模块-shared/tests/ -x  # 全量回归
```
