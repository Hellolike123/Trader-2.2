# 策略菜单：缠 · 威 · mi · 闸口包

> **状态**：思路菜单（非实现规格）  
> **版本**：v0.1 · 2026-07-18  
> **契约以** `strategy-pack.md` / `strategy-layered-architecture.md` **为准**

---

## 1. 三套原典/教义都有策略

| 体系 | 策略气质 | 在系统中 |
|------|----------|----------|
| 缠论 | 买卖点 + 级别 + 中枢 | 分析卡 + entry 包 |
| 威科夫 | 阶段 + 事件 + 地板止损 | 分析卡 + manage/stop |
| mi | 趋势纪律 + 仓位/四不做 | mistery_gate（已嵌入）；策略包脱敏名「趋势纪律」 |

系统定位：**多理论辅助**，非单一原典复刻。

---

## 2. 推荐包菜单（A～G → 闸口）

| 菜单 | 闸口 | 建议 id | 积木 |
|------|------|---------|------|
| G 空仓观察 | select | `select.observe_G` | 不新开、缺数、大盘差 |
| E 防守否决 | select | `select.defense_E` | SOW/破位、资金差、套牢+弱支撑 |
| B 结构试探 | entry | `entry.chan_buy1_probe` | 一买/底背驰、低吸区 |
| C 突破回踩 | entry | `entry.breakout_pullback` | 三买/SOS、回踩 |
| D 中线回踩 | entry | `entry.mid_pullback` | 生命线/回踩区、中线看法 |
| A 移动止损 | manage | `manage.wyckoff_trail` | 地板、成本、S1–S3 |
| F 高位减仓 | take | `take.partial_F` | 浮盈、压力、BC/UT |
| 止损全清 | stop | `stop.invalidate_full` | 破地板/失效 |

落地顺序：**G → E → B → A → stop 文案 → D/F/C**。

---

## 3. 状态 → 主用示意

| 状态简化 | 主用倾向 |
|----------|----------|
| 不新开 / 很差 / SOW+支撑弱 | G 或 E |
| 一买+低吸+资金尚可 | B（常 plan） |
| 三买回踩 | C |
| 中线可跟踪+回踩区 | D |
| 已持仓 | A ± F |
| 浮盈大近压力 | F 为主 |

---

## 4. 威科夫 trail 摘要

S1 地板−缓冲 → S2 保本 → S3 新波谷；止损全清；止盈可分。  
原典无「固定 −7%」主判决；那是工程熔断，另口径。

---

*扩展新包时：先填 strategy-pack 字段模板，再挂闸口与测试 ID。*
