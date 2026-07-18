# 策略包（Strategy Pack）契约

> **状态**：设计稿（未强制实现）  
> **版本**：v0.1 · 2026-07-18  
> **上级架构**：`strategy-layered-architecture.md`  
> **落地测试**：`strategy-roadmap-and-tests.md`

---

## 1. 一句话

```text
分析（状态 + 数字）→ 按闸口匹配策略包库 → 报告 📐 展示主用/候选（填实价格）
```

策略内容由人编写；系统 **对号入座 + 填数 + 展示**，禁止 LLM 在 `build_report` 路径临场编规则。

---

## 2. 策略包最小字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `id` | 稳定唯一 | `manage.wyckoff_trail` |
| `name` | 展示名 | 威科夫移动止损 |
| `gate` | 所属闸口 | `manage` \| `entry` \| `select` \| … |
| `version` | 版本 | `1.0` |
| `summary` | 一句话 | 波谷地板；止损全清；止盈可分 |
| `match` | 适用条件 | 见 §4 |
| `exclude` | 禁用条件 | |
| `priority` | 同闸排序，越大越优先 | `100` |
| `stages` | 可选阶段 | S1/S2/S3 |
| `stop_rules` | 止损算法与纪律 | 全清 / 缓冲 |
| `take_rules` | 止盈 | 可分仓 |
| `report_template` | 展示键 | |
| `lineage` | 血统标签 | `wyckoff` \| `chan` \| `mi` |
| `motto` | 可选口诀 | 逃生全清 · 收成分批 |

存放（Arch D）：

- 仓库：`trader_shared/strategy/packs/*.yaml`  
- 用户覆盖（可选后续）：`~/.trader/strategy_packs/`

---

## 3. 匹配结果

```text
per_gate:
  select:  { primary, candidates[], mode }
  entry:   { primary, candidates[], mode }   # mode: plan | active | off
  manage:  …
rejected:  [{ id, gate, reason }]            # 可选调试
```

- `mode=plan`：未持仓或不新开 → 仅预案，禁止「现在买入」语气  
- `mode=active`：已持仓或明确允许执行  
- `primary=null`：该闸无适用包；select 可回落 G  

---

## 4. 匹配逻辑

```text
1. 加载包库，按 gate 分组
2. 每闸：match 且非 exclude → 候选
3. priority 排序 → primary + candidates（展示限 1 候选）
4. 应用互斥（architecture §3.1）
5. bind 数字 → Execution View
6. 渲染
```

### 4.1 铁律

1. 纪律「不新开 / 仓 0% / regime 否决」→ entry 不得 active  
2. 策略 **不进** fusion `weighted_score`  
3. 策略止损若展示，须标注规则名；不静默覆盖结构引擎事实价 unless 产品明确  
4. 无匹配不编造  

### 4.2 条件表达（示意）

```yaml
match:
  all:
    - field: has_position
      eq: true
    - field: has_support_floor
      eq: true
exclude:
  any:
    - field: action_kind
      in: [block_new]
```

字段表在实现前冻结（见 roadmap §分析意见卡）。

---

## 5. Execution View（填数后）

| 字段 | 说明 |
|------|------|
| `gate` / `pack_id` / `mode` | |
| `stage_id` | S1/S2/…/none |
| `stop_price` / `stop_policy` | 如「全清」 |
| `floor_price` | 地板 |
| `next_conditions` | 下一阶段人话 |
| `take_hints` | 分批参考价 |

---

## 6. 示例包：威科夫移动止损

- `id`: `manage.wyckoff_trail`  
- `gate`: `manage`  
- `lineage`: `wyckoff`  

| 阶段 | 进入 | 止损 |
|------|------|------|
| S1 | 成交或开仓预案 | 近回调低（地板）− 缓冲 |
| S2 | 浮盈覆盖摩擦（约 1%～2%，可配） | 上移至成本+费用 |
| S3 | 新高→回调→再破前高 | 新波谷 − 缓冲 |

缓冲示例：价>100 → −0.25；价<10 → −0.03；中间另配。

纪律：

- 止损触发 → **一次性全清**  
- 止盈 → **可分仓**；滞涨可主动减  
- 口诀：逃生全家跑；收成分批摘  

字段映射：地板 ← support / 近摆动低；参考止盈 ← 止盈区/压力。

---

## 7. 报告展示契约

```text
📐 策略
  买：…（plan|active）
  持：威科夫移动止损 · S1 · 止损 xx（全清）
  止损：证伪全清 @ xx
```

或未持仓：

```text
📐 策略
  选股：观察
  买：结构试探（预案）· 低吸区 … · 初始止损 …
  持：若开仓则按威科夫移动止损
```

微信红线：无 Markdown 标题/粗体/表格/水平线。

---

## 8. 模块落点（建议）

| 内容 | 路径 |
|------|------|
| 匹配 | `trader_shared/strategy/match.py` |
| 包 YAML | `trader_shared/strategy/packs/` |
| 渲染 | `report_core` 📐 闸口 |
| 单测 | `tests/test_strategy_match.py` 等 |

```text
report_builder → report dict
  → strategy_match(report, packs)
  → report_core render
```

---

## 9. 非目标

- 策略替换 fusion 三评委  
- 报告内嵌长篇原典教程  
- 自动下单  
- build_report 内 LLM 生成规则  

---

## 10. 开放问题

1. 中间价缓冲：ATR 还是跳点×N  
2. regime=很差：隐藏策略 vs 仅预案  
3. 持仓成本来源：池 / 参数 / 文件  
4. 包热更新：仅仓库 vs `~/.trader`  

---

*实现前以本文 + architecture + roadmap 三者一致为准。*
