# 融合层文档同步 — 规格

> 来源：commit 8d67b8b 及后续实现
> 状态：已实现，本文档记录 design doc 需要同步的差异

---

## 概述

`docs/designs/decision-fusion-layer.md` 是融合层的设计文档，但部分细节已与实际实现脱节。本文档列出所有需要同步的差异点。

---

## 差异清单

### 1. `merge_decisions()` 函数签名

**设计文档（旧）：**
```python
merge_decisions(chan_result, momentum_result, wyckoff_result, regime)
```

**实际实现（新）：**
```python
merge_decisions(
    chan_result,
    momentum_result,
    wyckoff_result,
    regime,
    hmm_regime,           # 新增: HMM 状态
    extend_fundamental,   # 新增: 基本面扩展数据
    extend_sentiment,     # 新增: 情绪面扩展数据
    current_price,        # 新增: 当前价格
    bars,                 # 新增: K线数据
)
```

### 2. `FUSION_LOG_ONLY` 默认值

**设计文档：** `"true"`
**实际实现：** `"false"`（fusion_core.py line 49）

说明：融合层已从观察模式切换为激活模式。

### 3. 输出 action 字符串

**设计文档示例：**
```json
{"action": "止跌确认才试，最多5%仓位"}
```

**实际 `_FUSION_ACTION_MAP` 值：**
- "半仓试 (多方主导)"
- "半仓试 (多方主导但有分歧)"
- "增持"
- "持股观望"
- "减仓"
- "空仓/止损"
- "空仓 (大盘很差, 一票否决)"
- "观望 (信号冲突)"
- "等转强 (多方主导但有分歧)"

### 4. 输出字段缺失

设计文档的输出 dict 缺少 `hmm_regime` 字段，实际实现会返回该字段。

### 5. 融合层分解日志（commit 8d67b8b）

设计文档示例用紧凑单行格式：
```
└─ 缠论底背驰(50%) + 动量中性 + 威科夫无信号
   加权: 0.18 | 大盘: 正常
```

实际实现用多行格式：
```
融合层：增持（评分 +0.35，置信度 45%）
大盘环境：正常（HMM: 多头）
  缠论：看多（置信 60%，权重 30%）
  动量：中性（置信 40%，权重 45%）
  威科夫：看空（置信 55%，权重 25%）
  注意：多信号存在分歧（分歧度 1.3），优先采纳缠论/威科夫方向
```

实际格式更详细，便于调试。建议更新设计文档示例。

---

## 设计文档中缺失的功能

以下功能已在代码中实现但设计文档未提及：

### 6. FUSION_STATUS_MAP（融合层→状态机桥接）

9 个映射关系，将融合层 action 映射为 status_layers 的 base_status：

```python
_FUSION_STATUS_MAP = {
    "半仓试 (多方主导)": "低吸观察",
    "半仓试 (多方主导但有分歧)": "等转强",
    "增持": "低吸观察",
    "持股观望": "等转强",
    "减仓": "冲高减仓",
    "空仓/止损": "暂不碰",
    "空仓 (大盘很差, 一票否决)": "暂不碰",
    "观望 (信号冲突)": "防守观察",
    "等转强 (多方主导但有分歧)": "等转强",
}
```

### 7. 融合覆盖机制

配置项：
- `FUSION_OVERRIDE_ENABLED` — 是否允许融合层覆盖状态
- `FUSION_CONFIDENCE_THRESHOLD` — 覆盖所需最低置信度

当融合层置信度超过阈值时，其 action 会通过 FUSION_STATUS_MAP 覆盖 status_layers 的判定。

### 8. Scenario Priority Filter

根据价格在 20 日区间的位置（pos_pct）动态调整信号权重：
- 价格在低位：增加缠论/威科夫权重
- 价格在高位：增加动量权重

### 9. 贝叶斯融合（bayesian_fusion.py）

独立的贝叶斯融合模块，与加权融合并行运行。

### 10. Veto 噪声消除

当信号分歧度过高时的降噪机制。

---

## 更新建议

在 `docs/designs/decision-fusion-layer.md` 中：
1. 更新 Section 4.2.2 的函数签名（差异 #1）
2. 修正 FUSION_LOG_ONLY 默认值（差异 #2）
3. 更新 Section 5 的输出示例（差异 #3, #5）
4. 添加 hmm_regime 到输出字段（差异 #4）
5. 新增 Section 描述 FUSION_STATUS_MAP 和覆盖机制（差异 #6, #7）
6. 新增 Section 描述 Scenario Priority Filter（差异 #8）
7. 简要提及贝叶斯融合和 Veto 机制（差异 #9, #10）
