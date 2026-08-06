# P0-1 信号结构化字段（消除融合层中文关键词脆弱匹配）

> 关联：architecture-review-2026-07-14.md → P0-1
> 目标：把融合层 `fusion_core.merge_decisions` 里 3 处「读 reason 中文关键词字符串」的脆弱匹配，改为读信号源在生成时就标好的 `signal_tier` 结构化字段。
> 原则：**行为零漂移**（等价性闸门验证），纯加字段 + 改 fusion 读字段，不动加权公式、不动 `weighted_score` 计算式。

---

## 1. 现状审计（已确认的全部匹配点）

融合层 `02-共享模块-shared/trader_shared/fusion_core.py`：

| 行 | 变量 | 当前逻辑（脆弱点） |
|----|------|-------------------|
| 622-624 | `strong_bullish_chan` | `chan_reason` 含 `一类买/二类买/三类买/1类买/2类买/3类买/底背驰/1st buy/2nd buy/3rd buy/bottom divergence` |
| 625-627 | `strong_bearish_chan` | `chan_reason` 含 `一类卖/1类卖/1st sell/顶背驰/top_divergence`（**不含二类卖/三类卖**——有意设计） |
| 632-637 | `strong_bearish_vpf` | `vpf_reason` 含 `天量/滞涨/连/流出` **或** `conf>=0.5` |

信号源：
- `chan_reason` ← `_chan_to_signal` 生成的 `reason` 字符串（该函数内部已用 `signal_type` 结构化，但 fusion 又回头解析 reason，冗余且脆）。
- `vpf_reason` ← `vpf_core.build_vpf_signal` / `vpf_to_fusion_signal` 生成的 `reason` 字符串。

**不在本 P0-1 范围内**：`momentum`、`wyckoff` 两路在融合加权路径里**不是**关键词匹配（momentum 走 direction+confidence 直读；wyckoff 已退出短线融合，见工作记忆）。为保持改动外科手术级、等价性可逐票证明，本 P0-1 只动被关键词匹配实际消费的 **chan + vpf** 两路；wyckoff/momentum 的 `signal_tier` 字段留作后续展示一致性增强（纯加法、零行为影响，可另排）。

---

## 2. 字段契约

新增共享模块 `trader_shared/signal_schema.py`：

```python
# signal_tier 语义枚举（字符串常量，向后兼容普通 dict）
class SignalTier:
    # 缠论
    CHAN_BUY_1 = "chan_buy_1"          # 一类买（底背驰）
    CHAN_BUY_2 = "chan_buy_2"          # 二类买（低点抬高）
    CHAN_BUY_3 = "chan_buy_3"          # 三类买（突破中枢）
    CHAN_BUY_LIKE2 = "chan_buy_like2"  # 类二买（回踩偏弱）—— 不强多
    CHAN_SELL_1 = "chan_sell_1"        # 一类卖（顶背驰）
    CHAN_SELL_2 = "chan_sell_2"
    CHAN_SELL_3 = "chan_sell_3"
    CHAN_TOP_DIVERGENCE = "chan_top_div"
    CHAN_BOTTOM_DIVERGENCE = "chan_bottom_div"
    CHAN_TREND_UP = "chan_trend_up"    # 拉升段（不强多）
    CHAN_TREND_DOWN = "chan_trend_down"# 回调段（不强空）
    # 价量资金
    VPF_BEARISH_WARNING = "vpf_bearish_warning"  # 天量/滞涨/连出/累计流出
    NEUTRAL = "neutral"

# fusion 强信号判定（与旧关键词集 100% 对齐）
CHAN_STRONG_BULL_TIERS = {CHAN_BUY_1, CHAN_BUY_2, CHAN_BUY_3, CHAN_BOTTOM_DIVERGENCE}
CHAN_STRONG_BEAR_TIERS = {CHAN_SELL_1, CHAN_TOP_DIVERGENCE}
```

`signal_strength`（强/中/弱/无）本 P0-1 **暂不引入**——当前 fusion 只区分「强/非强」二元，tier 已能表达，避免过度设计。后续若需要更细粒度再扩。

---

## 3. 改造清单

### 3.1 新增 `trader_shared/signal_schema.py`
如上契约 + 三函数：`chan_is_strong_bull(tier)` / `chan_is_strong_bear(tier)` / `vpf_is_bearish_warning(tier)`。

### 3.2 `fusion_core._chan_to_signal`（80-204）
每个 return dict 增加 `"signal_tier"`：
- 一类卖 → `CHAN_SELL_1`；二类/三类卖 → `CHAN_SELL_2/3`
- 一类买 → `CHAN_BUY_1`；类二买 → `CHAN_BUY_LIKE2`；二/三类买 → `CHAN_BUY_2/3`
- 顶背驰 → `CHAN_TOP_DIVERGENCE`；底背驰 → `CHAN_BOTTOM_DIVERGENCE`
- 拉升段/回调段 → `CHAN_TREND_UP/DOWN`；无信号 → `NEUTRAL`

（注：buy/sell 分支已有 `signal_type` 字段，tier 与之同源，只是补全覆盖 divergence/trend 分支。）

### 3.3 `vpf_core.build_vpf_signal` / `vpf_to_fusion_signal`
return dict 增加 `"signal_tier"`：
- 当 `reason` 含 `天量/滞涨/连/流出` 且 direction==-1 → `VPF_BEARISH_WARNING`
- 否则 `NEUTRAL`
- 抽 `_vpf_tier_from_reason(reason)` 纯函数，两处共用，`vpf_to_fusion_signal` 对已有 vpf 也重算（保证无论上游是否预填都一致）。

### 3.4 `fusion_core.merge_decisions` 622-637 改为读字段
```python
chan_tier = chan_signal.get("signal_tier", SignalTier.NEUTRAL)
strong_bullish_chan = chan_signal.get("direction") == 1 and chan_tier in CHAN_STRONG_BULL_TIERS
strong_bearish_chan = chan_signal.get("direction") == -1 and chan_tier in CHAN_STRONG_BEAR_TIERS

vpf_tier = vpf_signal.get("signal_tier", SignalTier.NEUTRAL)
strong_bullish_vpf = vpf_signal.get("direction") == 1 and float(vpf_signal.get("confidence") or 0) >= 0.45
strong_bearish_vpf = vpf_signal.get("direction") == -1 and (
    float(vpf_signal.get("confidence") or 0) >= 0.5
    or vpf_tier == SignalTier.VPF_BEARISH_WARNING
)
```
缺失字段一律回退 `NEUTRAL`（= 旧逻辑「无关键词」），保证旧调用方不传 tier 也不崩、行为不变。

---

## 4. 等价性闸门（核心安全网）

新增 `tests/test_p0_signal_structurization.py`，用确定性 fixture 断言：

1. **tier 映射覆盖**：对 chan 每个分支、vpf 每种 reason 组合，验证 `signal_tier` 取值符合契约表。
2. **三布尔量等价**：构造 old-keyword-logic 函数 vs new-field-logic 函数，对 **chan×vpf 全组合矩阵**（direction∈{-1,0,1} × reason 关键词变体）断言 `strong_bullish_chan/strong_bearish_chan/strong_bearish_vpf` 完全一致。
3. **端到端零漂移**：用 mock 的 chan/vpf/momentum 信号喂 `merge_decisions`，对比「旧 reason 关键词」与「新 tier 字段」两条路径产出的 `weighted_score` + `action` 逐票一致（≥20 个代表场景：一类买+资金流出 / 类二买+天量 / 顶背驰+动量多 / 三类卖+中性 / 拉升段+流出 …）。

门禁：本测试加进 `scripts/run-gate-tests.sh` 的 TESTS 数组（新增离线测试须进门禁纪律）。

---

## 5. 风险与边界
- **vpf `连` 子串脆弱性**：`"主力连N日净流出"` 含 `连`，但 bullish 的 `"主力连N日净流入"` 因 direction==+1 不触发 `strong_bearish_vpf`，故等价无碍。此为旧代码既有潜在脆弱，P0-1 **原样复刻**，不在本次修复范围（避免引入行为漂移），后续可单独收紧。
- **回退安全**：任何调用方不传 `signal_tier` → 视为 `NEUTRAL` → 等价于旧「无关键词」，绝不改变既有行为。
- **不打扰展示**：report 仍读 `reason` 原文，tier 仅 fusion 内部消费。

## 6. 验收
- `tests/test_p0_signal_structurization.py` 全绿（含矩阵等价 + 端到端逐票一致）
- 完整 pre-push 门禁 94→（含新测试）全绿，零回归
- `weighted_score` 行为逐票无漂移（闸门证明）
