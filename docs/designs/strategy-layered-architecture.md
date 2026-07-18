# 分析 · 策略 · 决策 分层架构

> **状态**：已定方向（设计稿）  
> **版本**：v0.1 · 2026-07-18  
> **读者**：开发 Agent / 本人  
> **关联**：`strategy-pack.md`（策略包契约）· `strategy-roadmap-and-tests.md`（落地+测试）· `wyckoff-state-view.md`

---

## 1. 目标

不要做成「一个大策略万能」。更稳的是：

1. **分析层**解耦：缠论 / 威科夫 / 动量 / 筹码… 可单独查询  
2. **策略层**按 **6 个闸口**匹配包，每闸最多 **1 个主用包**  
3. **决策/报告层**合成展示，纪律只收紧  

```text
分析包(理论) → 策略闸口匹配 → 纪律只收紧 → 报告展示
```

---

## 2. 三层职责

| 层 | 回答 | 产出 | 禁止 |
|----|------|------|------|
| **分析 Analysis** | 现在是什么 | 状态灯、意见卡、关键价原材料 | 直接写「买 30%」 |
| **策略 Strategy** | 按哪套规矩管单 | 闸口主用包 + 止损/止盈/阶段 | 改 fusion 分数；无匹配硬编买入 |
| **决策 Decision + 报告** | 综合怎么办 | 动作、仓 cap、失效、📐 闸口卡 | 用策略覆盖「不新开」 |

### 2.1 与现状对照

| 能力 | 现状 | 目标 |
|------|------|------|
| 缠/动量/威插件 | `plugins/` 部分具备 | 统一「意见卡」schema |
| 筹码 | `chip_core` + 报告方案 C | 分析/展示包，默认不进 fusion |
| fusion | 缠+动+VPF 加权 | 保留为意见合成；逐步不替代闸口策略 |
| mistery_gate | 已收紧动作/仓 | 总纪律闸，展示脱敏（无 mi 品牌） |
| 策略包匹配 | **未落地** | 6 闸口 + 包库 |
| 报告 📐 | **未系统化** | 闸口主用/预案展示 |

---

## 3. 六闸口（交易生命周期）

```text
选股(入池) → 买(开仓包) → 持(管单包) → 加(仅允许条件) → 止盈(摘果) → 止损(证伪全清)
     ↑              ↑              ↑
  池规则         B/C/D          A ± F
  + G/E 否决    (未持仓)       (已持仓)
```

| 闸口 id | 名称 | 只回答 | 主用包示例 | 模式 |
|---------|------|--------|------------|------|
| `select` | 选股/入池 | 能否进池/留池 | 池规则；G 观察 / E 否决 | active |
| `entry` | 买/开仓 | 未持仓试不试 | B 结构试探 / C 突破回踩 / D 中线回踩 | plan \| active |
| `manage` | 持/管单 | 进去后怎么跟 | A 威科夫移动止损 | plan \| active |
| `scale` | 加仓 | 能不能加、上限 | 条件表（可非「包」） | allow \| deny |
| `take` | 止盈 | 摘多少 | F 高位减仓 | plan \| active |
| `stop` | 止损 | 跑不跑 | 与 A 共用地板；**触发=全清** | hard |

### 3.1 互斥与优先级（强制）

1. **stop 触发 > 一切**（不再谈加仓/分批死扛）  
2. **select 的 G/E 否决 > entry 执行**（否决后 entry 仅预案或关闭）  
3. **未持仓**：只强调 select + entry；manage/take/stop 可显示预案  
4. **已持仓**：entry 关闭或只读；主战场 manage + take + stop  
5. **每闸最多 1 个主用**；候选最多 1 行  

---

## 4. 分析层：理论包（意见卡）

理论 **不** 直接当策略包；输出固定小卡片供策略匹配。

| 包 | 意见卡字段（语义，实现时冻键名） | Skill 可单独问 |
|----|----------------------------------|----------------|
| chan | buy_type, sell_type, div, structure, dir | ✅ |
| wyckoff | phase, event, floor_hint, caution | ✅ |
| momentum | dir, conf, reason | ✅ |
| chip | support_tag, resist_px, trapped_tag | ✅ |
| vpf | dir, conf, reason（fusion 第三席） | 可选 |

公共上下文：`current, stop, zones, action_gate, regime, has_position, cost…`

**定位**：系统是「多理论辅助决策」，不是单一原典复刻；威科夫提供阶段/事件，缠提供结构，mi 纪律已在 gate。

---

## 5. 策略层：按闸口命名

```text
select.*   entry.*   manage.*   scale.*   take.*   stop.*
```

血统标签（chan / wyckoff / mi）仅作 metadata，**闸口为主键**。

最小包集（第一期）：

| id | 闸口 | 说明 |
|----|------|------|
| `select.observe_G` | select | 空仓观察兜底 |
| `select.defense_E` | select | 破位/派发否决 |
| `entry.chan_buy1_probe` | entry | 结构试探（B） |
| `manage.wyckoff_trail` | manage | 波谷地板移动止损（A） |
| `take.partial_F` | take | 分仓摘果（可二期） |
| `stop.invalidate_full` | stop | 证伪全清（文案+价） |

---

## 6. 决策与报告

- **纪律**（mistery_gate + chan_discipline）只收紧，优先于策略执行文案。  
- 报告结构建议：

```text
状态：结构 / 威 / 筹码 / 动能｜资金   ← 分析
动作：不新开 · 仓 · 失效              ← 纪律
📐 闸口：选股/买/持/止损…            ← 策略匹配结果
关键价…
```

- 未持仓：manage/take 用 **预案** 语气。  
- 微信：无 `#` / `**` / 表格 / `---`。

---

## 7. Skill 分工

| 场景 | 走哪层 |
|------|--------|
| 「威科夫现在什么状态」 | 分析 · wyckoff |
| 「一买怎么试」 | 策略 · entry 包（读 chan 卡） |
| 「综合怎么办」 | 决策报告（分析+策略+纪律） |

禁止：在纯分析 skill 里直接给重仓买入指令。

---

## 8. 文档索引

| 文档 | 内容 |
|------|------|
| **本文** | 分层 + 6 闸口架构 |
| `strategy-pack.md` | 包字段、匹配、威科夫 trail 草案 |
| `strategy-roadmap-and-tests.md` | 分期落地 + 测试清单 |
| `wyckoff-state-view.md` | 威科夫 View 契约（已有） |

---

*架构变更须同步本文与 roadmap；实现以代码与单测为准。*
