# 动量模块审计 + 修复记录（2026-07-16）

> 规格对齐缠论/威科夫审查：业务契约 → 代码落点 → bug → 修复。  
> 动量**不是**学说原典体系，而是 RSI/MACD/ADX/布林组合 + Supertrend 确认，进短线 fusion 第二席。

---

## 一、业务角色

| 项 | 约定 |
|----|------|
| 融合席位 | 第二席 momentum（正常权重约 0.30，场景矩阵可调） |
| 主入口 | `assess_momentum` / `momentum_strategy` → `{"momentum": {...}}` |
| 插件 | `MomentumPlugin`（`analyze_all` 注入 supertrend_direction） |
| 融合映射 | `_momentum_to_signal`：direction 定方向，score 定 U 型置信度 |
| 数据不足 | `direction=insufficient`, `score=None`, fusion conf=0（禁止假 50 中性） |

---

## 二、代码地图

| 文件 | 职责 |
|------|------|
| `momentum_core.py` | RSI/MACD/ADX/布林 + 打分/方向 |
| `plugins/momentum_plugin.py` | 插件包装 + Supertrend 确认 nudge |
| `fusion_core._momentum_to_signal` | 统一信号 |
| `plugin_registry.analyze_all` | 计算 supertrend 并传给动量 |
| `report_presentation` | 动能展示映射（含 insufficient→数据不足） |

---

## 三、审计发现 → 处理

| # | 问题 | 严重度 | 处理 |
|---|------|--------|------|
| 1 | Supertrend 与**空头**同向时 `score +8`，把空头推向中性 | 高 | 空头确认改为 `score -8` |
| 2 | 只改 score、不重映射 direction → 近阈值中性 +8 后 fusion 仍 direction=0 | 高 | 改分后按 65/35 重映射 direction |
| 3 | 中性偏多(≥55)/偏空(≤45) 不确认 | 中 | ST 同向近阈值也确认 |
| 4 | MACD 死叉当根 hist 仍可能为正，再 +「柱为正」 | 中 | `macd_death` 时不加柱为正 |
| 5 | ADX 强趋势与反向超买超卖对冲假中性 | 中 | 强 ADX 下逆向超额分减半 |
| 6 | success 路径缺 `strength`（仅 insufficient 有） | 低 | 补 strong/moderate/neutral |
| 7 | Plugin.weight=0.20 与文档 0.30 不一致 | 低 | 改为 0.30（实际权重仍以 fusion 矩阵为准） |
| 8 | fusion 仅 cap「bullish 且 score≤45」 | 低 | 对称 cap「bearish 且 score≥55」 |

---

## 四、未做（可接受）

| 项 | 说明 |
|----|------|
| 完整「动量原典」 | 无统一原典；属工程指标组合 |
| 改场景权重矩阵 | 需产品决策，非正确性 bug |
| OBV/量能动量独立席 | 已有 VPF 第三席，避免重复 |

---

## 五、不变量（后续 Agent）

1. `insufficient` ⇒ `score is None`，fusion conf=0。  
2. Supertrend **只确认不否决**；反向不动。  
3. 空头确认必须**减分**，多头确认加分。  
4. 改分后必须重映射 `direction`（与 assess 阈值一致）。  
5. 行为变更补 `test_momentum_core` + 本文件。

## 六、自测

```bash
export PYTHONPATH=02-共享模块-shared
python -m pytest 02-共享模块-shared/tests/test_momentum_core.py -q
```
