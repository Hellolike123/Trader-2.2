# 融合层决策接入 build_signal

**日期**: 2026-05-12
**状态**: 设计阶段

---

## 问题

融合层已完成并在 `build_report()` 中输出到 `report["fusion"]`，但 `build_signal()` 完全依赖 `signal_state()` 的 scene 决策。融合层有信息但没被用上。

## 方案

在 `build_signal()` 中，融合层置信度足够高时优先使用融合决策。

### 改造点

修改 `run_analysis.py` 的 `build_signal()` 函数。

### 置信度阈值：0.2

`fusion.confidence` 范围是 `0.009 ~ 0.95`（`compute_confidence()` 输出）。
- 0.2 ≈ 模块方向一致但分数不高，值得信任
- 0.009 ≈ 全模块中性（今天无信号），不值得信任
- 阈值 0.2 是保守初始值，可在后续校准

边标：`== 0.2` 走 scene 路径（不踩融合）。

### 介入条件

```
1. report["fusion"] 存在且是 dict
2. fusion.confidence > 0.2
3. fusion.signals_detail 存在且不全为 0
4. ok → 用融合
5. 任一不满足 → fallback 到 scene
```

### 映射

| Fusion action | signal_type | direction | action |
|--------------|-------------|-----------|--------|
| 半仓试 / 增持 | `track` | `bullish` | `track` |
| 持股观望 | `wait_for_confirmation` | `bullish_lean` | `observe` |
| 减仓 / 空仓/止损 | `defensive` | `bearish` | `wait` |
| (不在表中) | 保留 scene | 保留 scene | 保留 scene |

### 输出

场景和融合信号同时保留，signal dict 新增 `fusion_override: bool` 字段表示是否被融合覆盖：

```python
signal = {
    "signal_id": ...,
    "signal_type": ...,
    "fusion_override": True,  # 新增
    # ... 其余字段不变
}
```

### 错误处理

```python
fusion = r.get("fusion")
if fusion and isinstance(fusion, dict):
    fc = fusion.get("confidence", 0)
    sd = fusion.get("signals_detail", {})
    has_signal = any(v.get("direction") != 0 for v in sd.values())
    if fc > 0.2 and has_signal:
        # 用融合决策
        sig_type, direction, sig_action = _map_fusion_to_signal(fusion.get("action", ""))
```

`_map_fusion_to_signal()` 未匹配时返回 `(None, None, None)`，调用方检测到 None 则保留 scene。

### 不改动

- `signal_state()` — 纯函数，保留供 fallback
- 报告模板 — `scene` / `state_label` 字段不动
- `build_watch_alert()` — 独立路径，不改

## 测试

| 场景 | 预期 |
|------|------|
| fusion.confidence=0.5, action=增持 | signal_type=track, direction=bullish |
| fusion.confidence=0.1 | 保留 scene（阈值以下）|
| fusion.confidence=0.2 | 保留 scene（边界）|
| report 无 fusion 字段 | 保留 scene（错误保护）|
| fusion 方向与 scene 一致 | 保留 scene（方向不变不切换）|
| fusion.action 不在映射表 | 保留 scene（未知 action 不覆盖）|
| fusion 有 action 但 signals_detail 全为零 | 保留 scene（空信号不覆盖）|

## 风险

- `build_signal()` 输出影响 `signals.jsonl` → `review-trader` / `trader-pool` / `trader-portfolio` 读取 `signal_type` 和 `direction`。融合覆盖后可能改变这些下游的输入。**缓解**: 新增 `fusion_override` 字段让下游可区分来源。
