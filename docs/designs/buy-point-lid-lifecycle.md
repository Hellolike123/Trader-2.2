# 买点「盖」生命周期（产品契约）

> **状态**：L1 已落地（展示 + failed 收紧新开）· L2/L3 待做  
> **版本**：v0.2 · 2026-07-18  
> **实现**：`trader_shared/buy_point_lifecycle.py` + `report_builder` / `report_core`
> **读者**：策略 / 纪律 / Agent  
> **边界**：不进入 `assess_momentum` 打分；不改 `weighted_score` 公式。

---

## 1. 一句话

**「盖」是买点是否仍有效的证伪线**（通常为站上后的关键支撑/中枢下沿/站上确认位）。  
生命周期回答的是：**这个买点还算不算数**，不是动能强弱。

---

## 2. 产品规则（与用户表一致）

| 情况 | 怎么算 | 状态转移 |
|------|--------|----------|
| 收盘在盖下 | **失败**，取消买点 | `active` → `failed`（作废） |
| 盘中刺穿盖下，收盘又回到盖上 | **先不判死**，继续看 | 保持 `active`（或 `watching`） |
| 收盘在盖下，次日立刻大阳站回 | **仍先当失败处理过**；若再站上，须重新走「站上 → 再回踩」，**不是接着旧买点** | `failed` 后新序列 → 新 `buy_point_id`，禁止复用旧 id |

### 2.1 判定粒度

- **证伪只看收盘**：盘中刺穿不单独判失败（与表第 2 行一致）。  
- **站回不算复活旧买点**：失败日之后的任何收盘站上，只允许开**新**生命周期。

### 2.2 与现有模块的关系

| 模块 | 关系 |
|------|------|
| `detect_buy_points` / 缠论 | 产「类型/价」；**不**管失效日 |
| `chan_discipline` C1 `short_trigger` | 今日是否「有买点类型」；**应**将来叠加 `buy_point_valid` |
| `mistery_gate` 失效文案 | 持仓/止损叙事；**不是**买点盖 FSM |
| `decision_core` 假跌破 | 止损层；**不是**开仓买点盖 |
| `assess_momentum` | **禁止**用 RSI 分数代替盖生命周期 |

---

## 3. 建议状态机（实现时）

```text
none ──(出现买点+站上确认)──► active
active ──(收盘 < 盖)──► failed
active ──(盘中破盖、收盘≥盖)──► active   # 不判死
failed ──(重新站上+再回踩完成)──► active'  # 新 id，非旧票复活
failed ──(超时/换结构)──► none
```

### 3.1 建议字段（未来写进 report / analysis_cards 或 discipline）

```text
buy_point_lifecycle:
  status: none | active | failed | watching
  lid_price: float | null          # 盖
  signal_id: str | null            # 与 Signal Contract 对齐
  failed_date: date | null
  note: str                        # 人话一行
```

- `short_trigger` 真绿条件建议：`有买点类型 AND status==active`（失败日不得绿）。  
- 策略闸 `entry`：`status==failed` → 不得 `active` 执行（最多 plan 文案「买点已失效，须重走」）。

---

## 4. 闸口契约挂钩（P1 扩展 · 未实现）

见 `strategy-gates.md` §2.2 增补。摘要：

| 闸 | 读 | 写/约束 |
|----|-----|---------|
| **entry** | `buy_point_lifecycle.status`, `lid_price` | failed → 禁止 executable；文案区分「无买点」vs「买点已失效」 |
| **select** | 可选：连续 failed 记观察 | 不否决全池，仅笔记 |
| **stop** | 无直接绑定盖 | 持仓止损仍走结构 stop |

**禁止**：策略包内重算笔/盖价；只读分析层给出的 `lid_price` + status。

---

## 5. 落地分期

| 阶段 | 内容 | 完成定义 |
|------|------|----------|
| **Spec** | 本文 | ✅ |
| **L1 展示** | 报告一行：买点有效/已失效（盖 xx） | ✅ `buy_point_lifecycle` + 短线区渲染 |
| **L1b 纪律** | failed → allow_new=False、清单缺「买点已失效」 | ✅ report_builder |
| **L2 持久化** | failed 后跨日禁止接旧 signal_id | 待做 |
| **L3 闸口** | entry pack 匹配读 lifecycle | 待做 |

---

## 6. 测试清单（实现时）

| ID | 用例 | 期望 |
|----|------|------|
| L-01 | 收盘 &lt; 盖 | status=failed，C1 买点不绿 |
| L-02 | 盘中 &lt; 盖，收盘 ≥ 盖 | status 仍 active |
| L-03 | 失败日后大阳站上 | 新 signal_id，非旧 id |
| L-04 | failed + 清单其它全绿 | 仍「新开：否」，缺项含买点失效类文案 |
| L-05 | 动量 score 90 但 failed | fusion 可偏多，**纪律仍不新开** |

---

## 7. 相关

- 开仓清单：`chan_discipline.build_entry_checklist`  
- 闸口：`docs/designs/strategy-gates.md`  
- 边界：`docs/designs/analysis-strategy-boundaries.md`（策略不重算）  
