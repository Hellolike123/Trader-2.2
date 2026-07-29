# Fusion Guide — 融合层字段解读

merge_decisions() 返回的融合字段解读规则。

## 融合字段速查

| 字段 | 类型 | 范围 | 含义 |
|------|------|------|------|
| `weighted_score` | float | [-1.35, 1.35] | 融合加权分。正=多方，负=空方 |
| `confidence` | float | [0, 1] | 综合置信度 |
| `action` | str | — | 建议动作（由 weighted_score + regime 映射） |
| `regime` | str | 正常/偏弱/很差/未知 | 大盘环境 |
| `hmm_regime` | str | bull/bear/range | HMM 前瞻大势状态 |
| `disagreement` | float | [0, 3] | 三路信号分歧度（max - min direction） |
| `signals_detail` | dict | — | chan/momentum/wyckoff 各自的 direction + confidence |
| `weights_used` | dict | — | 实际使用的权重分配 |

## 8 档阈值（weighted_score → 方向强度）

| weighted_score | 方向 | 输出用语 |
|----------------|------|---------|
| ≥ 0.40 | 强多 | 趋势明确，可持仓 |
| ≥ 0.25 | 偏多 | 偏多操作，轻仓试探 |
| ≥ 0.10 | 弱多 | 弱势偏多，等确认 |
| ≥ -0.05 | 中性 | 观望，等信号 |
| ≥ -0.12 | 弱空 | 弱势偏空，谨慎 |
| ≥ -0.25 | 偏空 | 偏空操作，逐步减仓 |
| ≥ -0.40 | 强空 | 趋势向下，回避 |
| < -0.40 | 极空 | 远离，等待企稳 |

## action 字段映射（score_to_action）

action 由 `score_to_action(weighted_score, disagreement, regime)` 生成：
- `disagreement > 1` 且无强信号 → "观望 (信号冲突)"
- `regime=很差` → "暂不碰"
- `regime=偏弱` → 所有买入建议降一档

**禁止用 action 字符串推断方向**。产品出手听 `decision_view`（共振∧策略∧纪律）；`weighted_score` 仅 fusion 仪表偏多/偏空，不作总司令。

## 覆盖机制（Post-Processing Overrides）

action 生成后可能被以下机制覆盖（按优先级）：

1. **解禁风险一票否决**（unlock_veto）→ "空仓 (限售解禁风险)"
2. **资金连续流出一票否决**（fund_flow_outflow_veto）→ "资金流出，减仓观望"
3. **天量天价**（volume_warning climactic）→ "天量天价，减仓观望"
4. **高位修正**（pos_pct ≥ 0.8 + 观望类 action）→ "高位观望"

被覆盖后，`weighted_score` 和 `confidence` 仍保留原始值（不修改），仅 action 被改写。

## verbatim 模板（AI 不可改写）

build_report() 会生成 `fusion_verbatim` 字段，AI 输出时必须逐字引用，不可改写。

格式：`{emoji} {action}｜置信{confidence}%｜加权分{weighted_score}｜{regime}`

示例：
- 🟢 增持｜置信 62%｜加权分 0.28｜正常
- 🟡 等转强｜置信 41%｜加权分 0.08｜偏弱
- 🔴 暂不碰｜置信 85%｜加权分 -0.35｜很差
- ⚪ 观望｜置信 30%｜加权分 -0.02｜正常

emoji 由 weighted_score 决定：≥0.25 🟢 / ≥0.10 🟡 / ≥-0.05 ⚪ / ≥-0.12 🟠 / else 🔴

## 权重分配

### 默认权重（由 regime 决定）
| regime | chan | momentum | wyckoff |
|--------|------|----------|---------|
| 正常 | 0.33 | 0.34 | 0.33 |
| 偏弱 | 0.40 | 0.20 | 0.40 |
| 很差 | 0.50 | 0.10 | 0.40 |

### 场景偏置（覆盖默认）
| 场景 | chan | momentum | wyckoff |
|------|------|----------|---------|
| 低位突破 (pos_pct ≤ 0.3) | 0.44 | 0.20 | 0.36 |
| 高位超买 (pos_pct ≥ 0.7 + mom≥80) | 0.20 | 0.56 | 0.24 |
| 结构看空警告 | 0.44 | 0.20 | 0.36 |

### 主力行为修正
| main_force_env | chan | momentum | wyckoff |
|----------------|------|----------|---------|
| accumulation (吸筹) | +0.00 | -0.10 | +0.10 |
| testing (试盘) | +0.00 | +0.00 | +0.00 |
| markup (拉升) | -0.05 | +0.10 | +0.00 |
| distribution (派发) | -0.10 | -0.05 | +0.10 |
| markdown (砸盘) | -0.15 | -0.10 | -0.10 |
