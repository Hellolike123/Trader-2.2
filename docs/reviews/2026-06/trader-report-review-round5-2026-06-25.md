# Trader 报告五轮体检 — 运维工具链失效 + 边界检查

体检时间：2026-06-25 02:10
累计发现：四轮 87 项 + 本轮 8 项 = 95 项

本轮重点：AGENTS.md 宣称的运维工具链实际是否能跑、track 信号追踪是否真的工作、compare 输出是否够用。

---

## V. AGENTS.md 宣称工具链的实测结果

### V1. run_trader.py（中央指挥官）— 直接 import 失败 ⚠️ P0 必修

**AGENTS.md 宣称**：`run_trader.py` 是"全局中央指挥官路由器，统一路由盘中/盘后指令"

**实测**：

```bash
$ python3 scripts/run_trader.py --help
ModuleNotFoundError: No module named 'trader_shared'
```

**根因**：`scripts/run_trader.py` 用 `import trader_shared`，但 `scripts/` 目录不在 sys.path 里。`trader.py` 能正常工作是因为它在入口处执行了 `sys.path.insert(0, str(SHARED_DIR))`。

**修复**：在 `import trader_shared` 前加上：
```python
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "02-共享模块-shared"))
```

---

### V2. t0_cron.py（crontab 盯盘入口）— 同样 import 失败 ⚠️ P0 必修

**AGENTS.md 宣称**：`t0_cron.py` 是"T0 盯盘 cron 入口，适合 crontab 每 5 分钟调用"

**实测**：

```bash
$ python3 scripts/t0_cron.py --help
ModuleNotFoundError: No module named 'trader_shared'
```

**根因**：同 V1，`import trader_shared` 找不到模块。

**影响**：如果用户按 AGENTS.md 的建议配了 crontab，会每 5 分钟收到报错而不是盯盘结果。

**修复**：同 V1，在 import 前注入路径。

---

### V3. track 命令返回空结果，但 signals.jsonl 有 102 条信号 ⚠️ 必修

**AGENTS.md 宣称**：`trader track` 是"信号准确率追踪"

**实测**：

```bash
$ python3 trader.py track --days 7
📊 信号追踪面板
指定时间范围内无结果。
```

但 `signals.jsonl` 有 102 条信号，最新的是 2026-06-24（昨天）。

**根因**：track 命令可能读取了错误的数据源（例如读的是 `signal_results.jsonl` 而非 `signals.jsonl`），或者日期过滤逻辑有 bug。

**修复**：排查 `final_tracker.py` 的数据源路径和日期过滤逻辑。

---

### V4. compare 命令输出过分简略 ⚠️ 必修

**实测输出**（江西铜业 vs 赣锋锂业）：

```
对比 — 江西铜业 vs 赣锋锂业

🌍 大盘正常 | 中证1000 MA5/MA20 < 趋势偏空 今日+0.7% (HMM前瞻: 低波上涨)

1. 江西铜业  承接存在  47.33元  波幅偏高(7%)
   首仓≤5% | 止损 45.71元
   融合:等转强观察 | 置信度0.093

2. 赣锋锂业  冲高减仓  71.62元  波幅偏高(5%)
   首仓≤5% | 止损 70.13元
   融合:减仓 | 置信度0.153

👉 同等条件下，优先选波动小的
```

**问题**：对比应该是最重要的选股决策输出，但当前只有行情摘要，缺少：
- 五层打分对比（结构/量价/筹码/动能）
- 筹码分布对比
- 主力行为对比
- 盈亏比对比
- 阶段-动能对比
- **为什么选 A 不选 B 的量化理由**

**修复**：compare 增加表格化对比维度，最后给出量化排序结论。

---

## W. 其他发现

### W1. quick_change.py --help 无输出内容 ⚠️

**实测**：

```bash
$ python3 scripts/quick_change.py --help
# 空输出，exit=0
```

help 虽然能显示 usage（需要传 --type 才会报错），但没有 -h 就无输出，不符合 CLI 惯例。

**修复**：`--help` 应显示完整帮助信息。

---

### W2. track 命令读到的信号数据只有 1 条测试数据（人工回填）

**现象**：`signal_results.jsonl` 只有 1 条记录：

```json
{"signal_id": "test_active_signal_12345", "outcome": "win", "source": "manual_backfill"}
```

而 `signals.jsonl` 有 102 条信号。track 命令可能读取的是 `signal_results.jsonl` 而不是 `signals.jsonl`，导致看不到任何真实信号。

**修复**：track 命令应统一读取 `signals.jsonl`（含 outcome 字段），不需要单独的 `signal_results.jsonl`。

---

### W3. signal_log.jsonl.bak 暴露了旧架构问题 ⚠️

**现象**：backup 文件中的信号格式与当前 `signals.jsonl` 不同：

```
旧格式: signal_id_md5 + signal_id (两套 ID)
新格式: signal_id (SHA256 强一致)
旧数据: outcome_pnl_pct=-2.01 但 outcome="unknown"
```

**问题**：
1. 旧数据的 outcome 有值（-2.01%）但 outcome 字段仍是 "unknown"，说明回填逻辑只写了 pnl 没写 outcome
2. 旧格式和新格式并存，cleanup 不完整
3. `.bak` 文件应该被迁移或删除，不应该还留在 `~/.trader/`

---

### W4. 所有旧信号 outcome_pnl_pct=-2.01 完全一致 ⚠️

**现象**：`signal_log.jsonl.bak` 中连续 5 条信号 `outcome_pnl_pct=-2.01`。

**问题**：不同日期的信号不可能 all -2.01%——说明回填使用了固定值或错误的计算逻辑。

**修复**：排查回填逻辑，确保 outcome_pnl_pct 基于实际持仓后的价格变化计算。

---

## X. 总结

五轮累计 95 项问题：
- 第一轮：14 项（跨视图数据、信息密度、格式）
- 第二轮：26 项（数学矛盾、严重 bug、逻辑断层）
- 第三轮：25 项（数据通道污染、JSON 内部矛盾、信号生命周期）
- 第四轮：22 项（代码 bug、功能空壳、缓存失效、测试缺失）
- 第五轮：8 项（运维工具链、track/compare 失效、旧数据污染）

**本轮 P0 优先修复**：
1. V1+V2（10 分钟）：run_trader.py 和 t0_cron.py 的 import 路径修复（同四轮 N1 模式）
2. V3（30 分钟）：track 命令数据源修复
3. V4（1 小时）：compare 增加对比维度
4. W2（10 分钟）：track 统一读 signals.jsonl
