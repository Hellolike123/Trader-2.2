# 选股池融合层集成（可见性）

**日期**: 2026-05-12

## 目标

池记录存储融合层输出，在 show/compare/rank 中展示，不改变评分逻辑。

## 改动

### 1. pool.json 记录新增字段

```python
{
    "fusion_action": "增持",          # merge_decisions() action，无融合时为 None
    "fusion_confidence": 0.6,         # 0~1，无融合时为 None
    "fusion_score": 0.35,            # weighted_score，无融合时为 None
}
```

旧记录无这些字段时值为 None。

### 2. record_from_report() — 存储

```python
def record_from_report(report):
    fusion = report.get("fusion", {}) or {}
    record = {
        ...
        "fusion_action": fusion.get("action"),
        "fusion_confidence": fusion.get("confidence"),
        "fusion_score": fusion.get("weighted_score"),
    }
    return record
```

`fusion.get()` 在 key 不存在时返回 None。

### 3. cmd_show() — 单行内融合信息

`cmd_show()` 当前是紧凑单行列表（每只票一行）。融合信息放在行内：

```
南网科技(688248)  | 场景:防守观察(5)  ATR:3.07(5%)  | 融合:增持(0.6)
```

融合信息只在有 `fusion_confidence` 时显示，否则不显示。

### 4. cmd_rank() — 排序

`cmd_rank()` 在现有排序后增加**融合置信度作为次级排序键**（降序）。现有 `sort_items()` 加 `sort_key` 参数：

```python
sort_items(items, sort_key=lambda i: i.get("fusion_confidence") or 0, ...)
```

旧记录 fusion_confidence=None → 排末尾。

### 5. cmd_compare() — 对比块

`cmd_compare` 是块状布局（非表格）。每个股票块末尾追加一行融合信息：

```
融合决策: 增持（置信度 0.6）← 仅在 fusion 存在时显示
```

### 6. 融合与现有 pool 评分的关系

池评分（缠论 45+威科夫 30+筹码 25）**不变**。融合层仅作为附加信息展示，不参与评分计算。后续如果需要改变评分逻辑，另开计划。

### 7. 测试

- record_from_report 含 fusion → 记录含三个字段
- record_from_report 无 fusion → 三字段为 None
- show 输出含融合行内信息
- rank 融合置信度高的排前
- compare 含融合块

## 风险

- pool.json 追加字段，旧记录无 fusion → None → 显示跳过，不报错
- sort_items 需加参数，现有调用（show 无排序、rank 有排序）不受影响
