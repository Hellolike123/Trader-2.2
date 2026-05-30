# 讨论结果 — 2026-05-30

## Skill 合并方案（已交给 agent 执行）

详见 `docs/skill-consolidation-plan.md`

## 本次讨论新增决策

### 1. 去掉利弗莫尔框架

现状：
- `livermore_rules.yml` 定义了 0-5 的 tier
- `modifier_rule_engine.py` 里有 `apply_livermore_scale()`
- `portfolio_core.py` 里计算 `livermore_tier` 存到结果里
- `portfolio_run.py` 排序时用 `livermore_score` 当 fallback

问题：
- tier 只是存着，没有真正参与仓位计算
- 仓位还是 ATR 决定的
- 四阶段框架已经取代了它的位置

决定：
- 合并完成后，清理利弗莫尔相关代码
- 删除 `livermore_rules.yml`
- 清理 `modifier_rule_engine.py` 里的利弗莫尔函数
- 清理 `portfolio_core.py` 里的 `livermore_tier` 计算
- 清理 `portfolio_run.py` 里的 `livermore_score` fallback
- 保留 `apply_score_modifiers`（非利弗莫尔功能）

### 2. 仓位管理规则

四阶段 + 一条硬规则：

蓄势期：0-30%（试探）
  第一笔 10% → 确认站稳支撑 → 加到 20%
  突破确认 → 阶段转主升

主升期：50-80%（重仓）
  突破确认 → 加到 40%
  回踩不破 → 加到 60%
  持续走强 → 最多 80%

派发期：0-30%（减仓）
  高位滞涨 → 减到 40%
  MACD 顶背离 → 减到 20%
  跌破关键位 → 清仓

衰退期：0%（空仓）

硬规则：持仓亏损时，禁止加仓

### 3. 缓存规则

盘中（9:30-15:00）：
  trader 日线K线 → 用缓存
  trader 实时行情 → 抓最新
  t0 实时行情 → 抓最新（不缓存）
  review 日线K线 → 用缓存

盘后/周末：
  所有数据用缓存

自动清理：
  交易日 15:00 清日线缓存 + 预缓存新数据
  quote TTL 5 分钟（自然过期）
  非交易日不清

手动清理：
  trader.py cache clear → 全部清
  trader.py cache clear --type daily → 只清日线

### 4. 板块共振（暂缓）

akshare 有板块数据（概念/行业/资金流向），但暂不做。
等其他改动完成后再考虑。

### 5. funda skill（未来）

基本面分析（股东/机构/解禁/题材）从 trader 中移除，未来单独做 funda skill。
