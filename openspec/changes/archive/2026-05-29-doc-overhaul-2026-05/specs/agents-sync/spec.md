# AGENTS 文件同步 — 规格

> 来源：综合多个 commit 的文档差距
> 状态：待更新

---

## 概述

`AGENTS.md` 和 `AGENTS_DEEP.md` 是 AI Agent 理解系统的主要入口。当前存在大量缺失和过时信息。

---

## AGENTS.md 更新清单

### 需要新增的内容

| 内容 | 位置建议 | 说明 |
|------|----------|------|
| 250日线趋势过滤 | "决策流程" 或新 Section | 年线下方一票否决的行为 |
| ATR 移动止损 | "止损策略" | trailing_stop 公式和开关 |
| 假跌破确认 | "止损策略" | 3日确认机制 |
| 分阶段退出 | "止损策略" | 三级升级逻辑 |
| status_layers() | "核心函数" | 替代旧的 status_for() |
| 融合覆盖机制 | "融合层" | FUSION_OVERRIDE_ENABLED |

### 需要更新的内容

| 内容 | 当前状态 | 更新为 |
|------|----------|--------|
| 双层状态模型 | 描述准确但缺新状态 | 补充 STATUS_SCORE 新增的 8 个状态 |
| 决策流程图 | 缺少融合层和年线过滤 | 添加完整流程 |

---

## AGENTS_DEEP.md 更新清单

### Section 2.3 "状态机"

**当前：** 描述旧的 `candidate_core.STATUS_SCORE`，标注为 legacy
**更新为：** 描述 `config.py` 中的实际 STATUS_SCORE，包含全部状态：

```
突破确认(85), 突破观察(75), 体系转强确认(88),
未确认转强(72), 转强不足(62), 承接存在(68),
修复观察(65), 空间偏紧, 低吸观察, 冲高减仓,
风险回避, 暂不碰, 中性整理, 防守整理, 临近确认,
均线修复, 防守观察
```

### Section 5.1 "核心函数"

**当前：** 描述 `status_for()` 返回 str
**更新为：** 描述 `status_layers()` 返回 dict：
```python
{
    "base_status": str,    # 基础状态
    "theory_status": str,  # 理论状态
    "status": str,         # 最终状态（兼容旧接口）
    ...
}
```

### Section 5.6.2 "Scenario Priority Filter"

**当前：** 未提及 HMM 增强
**更新为：** 添加 `hmm_regime` 参数说明

### `merge_decisions` 签名

**当前：** 4 个参数
**更新为：** 8 个参数（见 fusion-layer-sync spec）

### Section 8 "数据流图"

**当前：** 线性流程，缺融合层
**更新为：**
```
light_data.py (数据拉取, days=300)
    │
    ├── structure_core.py (ATR + 移动止损 + 支撑/阻力)
    │       │
    │       ├── decision_core.py:status_layers()
    │       │       │
    │       │       ├── _ma250_check()     ← 年线一票否决
    │       │       ├── _fake_break        ← 假跌破确认
    │       │       ├── _near_stop         ← 分阶段退出
    │       │       └── base_status + theory_status
    │       │
    │       └── fusion_core.py:merge_decisions()
    │               │
    │               ├── chan_result (缠论)
    │               ├── momentum_result (动量)
    │               ├── wyckoff_result (威科夫)
    │               ├── hmm_regime (HMM)
    │               └── → action + confidence + FUSION_STATUS_MAP
    │
    └── run_analysis.py (渲染 + 融合层分解日志)
```

---

## phase2-improvement-plan.md 更新

### C-13 标记为已修复

在 C-13 Section（line ~888）开头添加：

```markdown
> [RESOLVED] 2026-05-29 — commit 676ae0e
> 修复方案：TREND_MA_LONG 改为 250（年线），LOOKBACK_DAYS 改为 300。
> 同时新增 _ma250_check() 一票否决机制。
```

### 其他可能已修复的 issue

需要逐个确认以下 issue 的当前状态：
- C-12 `_pool_count`
- S-1 两条独立决策路径
- S-2 fusion_result 未返回到 status_for

---

## trader-refactor-plan.md 更新

### ATR 止损部分

**当前：** 描述静态止损 `stop_distance = ATR14 * 2`
**更新为：** 添加一节描述动态移动止损，说明两者的关系：
- 静态止损（hard_stop）：仍然存在，作为底线
- 移动止损（trailing_stop）：跟踪最高价，只紧不松
- 两者取 max 作为最终止损

### 删除或标注不存在的功能

`--atr` / `--no-atr` CLI flag 在实际代码中不存在，需要标注为"未实现"或删除。
