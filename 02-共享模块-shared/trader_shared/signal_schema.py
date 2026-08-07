"""信号结构化字段契约 (P0-1)。

背景: 融合层 fusion_core.merge_decisions 原先在冲突消解时, 对 chan/vpf 信号的
`reason` 中文关键词字符串做脆弱匹配 (一类买/天量/流出 ...)。本模块把"强信号"
判定上提为信号源在生成时就标好的 `signal_tier` 结构化字段, fusion 改为纯读字段,
消除字符串解析脆弱性。

等价性: 本模块常量与函数 100% 复刻旧的 reason 关键词匹配语义, 详见
docs/designs/p0-1-signal-structurization.md。缺失字段一律按 NEUTRAL 处理 (等价旧"无关键词")。

注意: momentum / wyckoff 两路不在融合加权路径的关键词匹配消费范围内
(momentum 走 direction+confidence 直读; wyckoff 已退出短线融合), 其 signal_tier
字段不在本 P0-1 范围, 后续按需扩展。
"""

from __future__ import annotations

from typing import Any


class SignalTier:
    """信号层级枚举 (字符串常量, 兼容普通 dict 存取)。"""

    # ── 缠论 ──
    CHAN_BUY_1 = "chan_buy_1"                 # 一类买 (底背驰·面积)
    CHAN_BUY_2 = "chan_buy_2"                 # 二类买 (低点抬高)
    CHAN_BUY_3 = "chan_buy_3"                 # 三类买 (突破中枢)
    CHAN_BUY_LIKE2 = "chan_buy_like2"         # 类二买 (回踩偏弱) —— 不强多
    CHAN_BUY_SOFT1 = "chan_buy_soft1"         # 类一买 (柱序列弱确认) —— 不强多
    CHAN_SELL_1 = "chan_sell_1"               # 一类卖 (顶背驰·面积)
    CHAN_SELL_2 = "chan_sell_2"               # 二类卖
    CHAN_SELL_3 = "chan_sell_3"               # 三类卖
    CHAN_SELL_LIKE2 = "chan_sell_like2"       # 类二卖 (反抽偏弱) —— 不强空
    CHAN_SELL_SOFT1 = "chan_sell_soft1"       # 类一卖 (柱序列弱确认/盘整背驰) —— 不强空
    CHAN_TOP_DIVERGENCE = "chan_top_div"      # 顶背驰
    CHAN_BOTTOM_DIVERGENCE = "chan_bottom_div"  # 底背驰
    CHAN_TREND_UP = "chan_trend_up"           # 拉升段 (不强多)
    CHAN_TREND_DOWN = "chan_trend_down"       # 回调段 (不强空)
    # ── 价量资金 ──
    VPF_BEARISH_WARNING = "vpf_bearish_warning"  # 天量/滞涨/连出/累计流出
    NEUTRAL = "neutral"


# 与旧关键词匹配 100% 对齐的强信号 tier 集合
# 旧 strong_bullish_chan: 一类买/二类买/三类买/底背驰 (不含类二买/趋势)
CHAN_STRONG_BULL_TIERS = {
    SignalTier.CHAN_BUY_1,
    SignalTier.CHAN_BUY_2,
    SignalTier.CHAN_BUY_3,
    SignalTier.CHAN_BOTTOM_DIVERGENCE,
}
# 旧 strong_bearish_chan: 一类卖/顶背驰 (不含二类卖/三类卖/趋势)
CHAN_STRONG_BEAR_TIERS = {
    SignalTier.CHAN_SELL_1,
    SignalTier.CHAN_TOP_DIVERGENCE,
}

# vpf 偏空关键词集 (天量/滞涨/流出)。注意: 旧逻辑曾含裸 "连",
# 会误命中"连续净流入"等偏多文案; 现改由 _vpf_reason_bearish 精确判定。
_VPF_BEARISH_KEYWORDS = ("天量", "滞涨", "流出")


def _vpf_reason_bearish(reason: str) -> bool:
    """判定 vpf reason 是否偏空 (复刻旧逻辑, 但收紧 `连` 子串匹配)。

    旧逻辑用裸 `"连" in reason`, 会误命中"连续净流入"/"连续涨停"等偏多文案。
    精确语义: `连` 仅当伴随净出/净流出且不含净进/净流入时才算偏空
    (覆盖旧文案"主力连3日净流出"与新人话"连3日净出"/"5日净出xxxx万")。
    """
    if any(k in reason for k in _VPF_BEARISH_KEYWORDS):
        return True
    # 新人话：5日净出 / 10日净出（金额可正可负写法都已去符号，关键词即可）
    if ("5日净出" in reason or "10日净出" in reason) and "净进" not in reason:
        return True
    # `连` 收紧: 仅"连续/连N日 净出/净流出"算偏空, 排除"连续净流入/净进"
    if "连" in reason and (("净流出" in reason) or ("净出" in reason)) and (
        "净流入" not in reason and "净进" not in reason
    ):
        return True
    return False


def chan_is_strong_bull(tier: Any) -> bool:
    return tier in CHAN_STRONG_BULL_TIERS


def chan_is_strong_bear(tier: Any) -> bool:
    return tier in CHAN_STRONG_BEAR_TIERS


def vpf_is_bearish_warning(tier: Any) -> bool:
    return tier == SignalTier.VPF_BEARISH_WARNING


def vpf_tier_from_reason(reason: Any) -> str:
    """从 vpf reason 字符串推导 signal_tier (纯函数)。

    仅当 direction==-1 语义的偏空 reason 命中偏空规则时才标 BEARISH_WARNING;
    fusion 调用方仍会再叠加 direction==-1 检查, 故此处只负责"关键词→tier"映射。
    """
    s = str(reason or "")
    if _vpf_reason_bearish(s):
        return SignalTier.VPF_BEARISH_WARNING
    return SignalTier.NEUTRAL
