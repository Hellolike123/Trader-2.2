# 决策融合层（Manager Agent）设计文档

> 最后更新：2026-05-12
> 状态：设计审查中
> 依赖：/office-hours 产出已确认

---

## 一、核心思路

**不动任何现有计算逻辑，只加一层"翻译器"。**

你的系统现状：
- 缠论/威科夫/动量 各自独立运行，各自产出分析报告
- **但决策引擎 `status_for()` 只看价格/均线/涨跌%**，不看三大分析模块的输出
- 结果：缠论发现了"一类买"，动量显示"强烈看多"，但最终状态仍由结构层决定 — 分析输出被浪费了

你要做的：
- 每个分析模块 → 统一输出 `[方向, 置信度, 理由]`
- 融合层做加权汇总 + 冲突检测 + 状态感知权重
- 最终输出：`{action, confidence, signals_detail, regime, disagreement}`
- **现有 `status_for()` 完全不动**，融合层是外挂的

---

## 二、现有代码结构（不变）

```
输入 (current, bars, change_pct, quote)
    │
    ├── 缠论分析 ── chan_core.py:399──┐
    │    chanlun_strategy()            │
    │    → {chanlun: {buy_points, ...}}│  ← 产出存在，decision 不用
    │                                  │
    ├── 动量分析 ── momentum_core.py   │
    │    momentum_strategy()           │
    │    → {momentum: {score, ...}}    │  ← score 存在，decision 不用
    │                                  │
    ├── 威科夫分析 ─ wyckoff_core.py   │
    │    wyckoff_strategy()            │
    │    → {wyckoff: {spring, ...}}    │
    │                                  │
    └── 结构层 ──── structure_core.py  │
         build_structure_context()     │  ← 唯一被 decision 用的
         → {status, levels, ...}       │
                   │                   │
                   ▼                   │
         decision_core.py:status_for() │
         → status: str                 │
                   │                   │
                   ▼                   │
         action_for()                  │
         → action: str                 │
                                        │  ← 融合层加在这里
                                        │  ▼
                                       ┌──────────────┐
                                       │ fusion layer │  ← 新代码
                                       │              │
                                       │ 汇总所有信号  │
                                       │ 加权+冲突检测 │
                                       │ State→Action  │
                                       └──────────────┘
```

**关键发现：** `status_for()` 完全不消费 `chanlun_strategy()` / `momentum_strategy()` / `wyckoff_strategy()` 的输出。这是你要填补的 gap。

---

## 三、数据流

```
┌─────────────────────────────────────────────────────────┐
│                    输入层（不动）                          │
│  load_market_snapshot() → quote + daily_bars + 5min     │
├─────────────────────────────────────────────────────────┤
│               分析模块（不动，已有独立输出）                │
│                                                         │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐       │
│  │ chan       │  │ momentum   │  │ wyckoff    │       │
│  │ buy_points │  │ score: 72  │  │ spring     │       │
│  │ trend_label│  │ direction  │  │ vol_div    │       │
│  │ divergence │  │ RSI/MACD   │  │            │       │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘       │
│        │               │               │               │
│  ┌─────┴───────────────┴───────────────┴────────────┐  │
│  │            融合层（新代码）                        │  │
│  │                                                  │  │
│  │  1. 信号标准化                                    │  │
│  │     chan → {direction:1, confidence:0.7, ...}   │  │
│  │     momentum → {direction:1, confidence:0.6,...}│  │
│  │     wyckoff → {direction:1, confidence:0.8,...} │  │
│  │                                                  │  │
│  │  2. 状态感知（Regime）                            │  │
│  │     大盘正常 → 动量权重 0.4, 缠论 0.3, 威科夫 0.3│  │
│  │     大盘偏弱 → 缠论 0.5, 动量 0.2, 威科夫 0.3   │  │
│  │     大盘很差 → 空仓                              │  │
│  │                                                  │  │
│  │  3. 加权汇总                                      │  │
│  │     weighted_score = Σ(direction × confidence × weight)│
│  │                                                  │  │
│  │  4. 冲突检测                                      │  │
│  │     max(signals) - min(signals) > threshold →   │  │
│  │       降级动作                                  │  │
│  └─────┬────────────────────────────────────────────┘  │
│        │                                                │
│        ▼                                                │
│  ┌────────────────────────────────────────────────────┐│
│  │  输出层（不动，校验不变）                            ││
│  │  render_markdown(report)                           ││
│  │  validate() → schema/v1.py                         ││
│  │  build_signal() → signals.jsonl                    ││
│  └────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

---

## 四、新文件设计

### 4.1 文件位置

```
02-共享模块-shared/02-候选逻辑-candidate/
    fusion_core.py          ← 融合层核心逻辑（~200行）
    fusion_regime.py        ← Regime→权重映射（~100行）
02-共享模块-shared/fusion.py         ← 顶层入口（不动）
```

### 4.2 `fusion_core.py` — 信号标准化 + 加权 + 冲突检测

```python
"""决策融合层：将各分析模块的独立输出加权汇总。

零修改现有代码。所有信号函数按统一接口运行，融合层消费其输出。

输入签名（与现有 strategy() 一致）:
    current: float
    bars: list[dict]
    change_pct: float
    quote: dict | None

信号标准化后统一输出:
    {
        "direction": 1 | 0 | -1,  # 1=看多, 0=中性, -1=看空
        "confidence": 0.0-1.0,    # 置信度
        "reason": str,            # 人类可读理由
        "raw_key": str,           # 来自哪个分析: chan/wyckoff/momentum
    }
```

#### 4.2.1 信号标准化函数

每个分析模块的现有输出必须映射到统一格式。**映射只读，不改原函数。**

**缠论信号映射：**

```python
def _chan_to_signal(chan_result: dict) -> dict:
    """将 chanlun_strategy() 的原始输出映射为统一信号。"""
    buy_points = chan_result.get("chanlun", {}).get("buy_points", [])
    divergence = chan_result.get("chanlun", {}).get("divergence", {})
    
    # 一类买（底背驰）→ 强力看多
    for bp in buy_points:
        if bp["type"] == "一类买":
            return {"direction": 1, "confidence": 0.8, "reason": "缠论一类买（底背驰）", 
                    "raw_key": "chan"}
        if bp["type"] == "二类买":
            return {"direction": 1, "confidence": 0.6, "reason": "缠论二类买（低点抬高）",
                    "raw_key": "chan"}
    
    # 底背驰信号
    if divergence.get("bottom_divergence"):
        return {"direction": 1, "confidence": 0.5, "reason": "缠论底背驰", "raw_key": "chan"}
    
    # 顶背驰 → 看空
    if divergence.get("top_divergence"):
        return {"direction": -1, "confidence": 0.5, "reason": "缠论顶背驰", "raw_key": "chan"}
    
    # 回调段/拉升段趋势
    trend = chan_result.get("chanlun", {}).get("trend_label", "")
    if "拉升段" in trend:
        return {"direction": 1, "confidence": 0.4, "reason": f"缠论:{trend}", "raw_key": "chan"}
    if "回调段" in trend:
        return {"direction": -1, "confidence": 0.4, "reason": f"缠论:{trend}", "raw_key": "chan"}
    
    return {"direction": 0, "confidence": 0.3, "reason": "缠论无明确信号", "raw_key": "chan"}
```

**动量信号映射：**

```python
def _momentum_to_signal(momentum_result: dict) -> dict:
    """将 assess_momentum() 的原始输出映射为统一信号。"""
    score = momentum_result.get("momentum", {}).get("score", 50)
    signals = momentum_result.get("momentum", {}).get("signals", [])
    
    direction = 0
    confidence = 0.2
    
    if score >= 70:
        direction = 1
        confidence = 0.8
    elif score >= 60:
        direction = 1
        confidence = 0.5
    elif score <= 30:
        direction = -1
        confidence = 0.8
    elif score <= 40:
        direction = -1
        confidence = 0.5
    
    reason = "、".join(signals[-2:]) if signals else "动量中性"
    
    return {"direction": direction, "confidence": confidence, 
            "reason": reason, "raw_key": "momentum"}
```

**威科夫信号映射：**

```python
def _wyckoff_to_signal(wyckoff_result: dict) -> dict:
    """将 wyckoff_analysis() 的原始输出映射为统一信号。"""
    if wyckoff_result.get("spring_signal"):
        return {"direction": 1, "confidence": 0.7, 
                "reason": f"威科夫弹簧:{wyckoff_result.get('spring_reason','')}",
                "raw_key": "wyckoff"}
    
    if wyckoff_result.get("bullish_volume_divergence"):
        return {"direction": 1, "confidence": 0.5,
                "reason": "威科夫看多量价背离", "raw_key": "wyckoff"}
    
    if wyckoff_result.get("bearish_volume_divergence"):
        return {"direction": -1, "confidence": 0.5,
                "reason": "威科夫看空量价背离", "raw_key": "wyckoff"}
    
    if wyckoff_result.get("upthrust_signal"):
        return {"direction": -1, "confidence": 0.6,
                "reason": "威科夫上冲回落", "raw_key": "wyckoff"}
    
    return {"direction": 0, "confidence": 0.2,
            "reason": "威科夫无明确信号", "raw_key": "wyckoff"}
```

#### 4.2.2 融合主函数

```python
def merge_decisions(
    chan_result: dict,
    momentum_result: dict,
    wyckoff_result: dict,
    regime: str,  # "正常" | "偏弱" | "很差"
) -> dict:
    """决策融合层核心函数。
    
    Args:
        chan_result: chanlun_strategy() 的返回值
        momentum_result: momentum_strategy() 的返回值
        wyckoff_result: wyckoff_strategy() 的返回值
        regime: market_env.py assess() → level 字段
        
    Returns:
        {
            "action": str,                    # 最终决策
            "confidence": float,              # 综合置信度 0-1
            "weighted_score": float,          # 原始加权分数
            "regime": str,                    # 市场状态
            "disagreement": float,            # 分歧度 0-2, >1 表示冲突
            "signals_detail": {               # 信号溯源
                "by_chan": {...},
                "by_momentum": {...},
                "by_wyckoff": {...},
            },
            "weights_used": {                 # 实际用的权重
                "chan": 0.3,
                "momentum": 0.4,
                "wyckoff": 0.3,
            },
        }
    """
    # 1. 信号标准化
    chan_signal = _chan_to_signal(chan_result)
    momentum_signal = _momentum_to_signal(momentum_result)
    wyckoff_signal = _wyckoff_to_signal(wyckoff_result)
    
    # 2. 获取 Regime 权重
    weights = _get_regime_weights(regime)
    
    # 3. 加权计算
    weighted_score = (
        chan_signal["direction"] * chan_signal["confidence"] * weights["chan"] +
        momentum_signal["direction"] * momentum_signal["confidence"] * weights["momentum"] +
        wyckoff_signal["direction"] * wyckoff_signal["confidence"] * weights["wyckoff"]
    )
    
    # 4. 分歧检测
    directions = [s["direction"] for s in [chan_signal, momentum_signal, wyckoff_signal]]
    disagreement = max(directions) - min(directions)  # 0=一致, 2=完全相反
    
    # 5. 决策映射
    action = _score_to_action(weighted_score, disagreement, regime)
    
    # 6. 置信度
    confidence = _compute_confidence(weighted_score, disagreement, weights)
    
    return {
        "action": action,
        "confidence": round(confidence, 3),
        "weighted_score": round(weighted_score, 3),
        "regime": regime,
        "disagreement": round(disagreement, 3),
        "signals_detail": {
            "chan": chan_signal,
            "momentum": momentum_signal,
            "wyckoff": wyckoff_signal,
        },
        "weights_used": weights,
    }
```

#### 4.2.3 Regime 权重映射

```python
# fusion_regime.py

# 权重矩阵：[大盘状态] × [分析模块]
# 每个矩阵是一组权重，和为 1.0
REGIME_WEIGHTS = {
    # 大盘好 → 动量占优（趋势延续）
    "正常": {
        "chan": 0.3,
        "momentum": 0.45,
        "wyckoff": 0.25,
    },
    # 大盘弱 → 缠论占优（结构优先）
    "偏弱": {
        "chan": 0.5,
        "momentum": 0.15,
        "wyckoff": 0.35,
    },
    # 大盘很差 → 全员空仓
    "很差": {
        "chan": 0.0,
        "momentum": 0.0,
        "wyckoff": 0.0,
    },
}

# 决策映射表：加权分数 → 动作
ACTION_MAP = {
    # 分歧 > 1 时降级一档
    "分歧降级": [
        (0.4, "买入半仓（多方主导但有分歧）"),
        (0.0, "观望"),
        (-0.1, "等转强（多方主导但有分歧）"),
    ],
    # 正常映射
    "正常": [
        (0.4, "半仓试（多方主导）"),
        (0.1, "增持"),
        (-0.05, "持股观望"),
        (-0.2, "减仓"),
        (-0.4, "空仓/止损"),
    ],
}

def _get_regime_weights(regime: str) -> dict:
    return REGIME_WEIGHTS.get(regime, REGIME_WEIGHTS["正常"])

def _score_to_action(score: float, disagreement: float, regime: str) -> str:
    # 大盘很差 → 一票否决
    if regime == "很差":
        return "空仓（大盘很差，一票否决）"
    
    # 分歧太大 → 降级动作
    if disagreement > 1:
        actions = ACTION_MAP.get("分歧降级", ACTION_MAP["正常"])
        for threshold, action in actions:
            if score >= threshold:
                return action
    
    # 正常映射
    actions = ACTION_MAP.get("正常", [])
    for threshold, action in actions:
        if score >= threshold:
            return action
    return actions[-1][1] if actions else "观望"
```

---

## 五、输出示例（南网科技）

### 场景：缠论看多 + 动量弱 + 大盘正常

```json
{
  "action": "止跌确认才试，最多5%仓位",
  "confidence": 0.45,
  "weighted_score": 0.18,
  "regime": "正常",
  "disagreement": 0,
  "signals_detail": {
    "chan": {
      "direction": 1,
      "confidence": 0.5,
      "reason": "缠论底背驰",
      "raw_key": "chan"
    },
    "momentum": {
      "direction": 0,
      "confidence": 0.3,
      "reason": "量价确认不足",
      "raw_key": "momentum"
    },
    "wyckoff": {
      "direction": 1,
      "confidence": 0.3,
      "reason": "威科夫无明确信号",
      "raw_key": "wyckoff"
    }
  },
  "weights_used": {
    "chan": 0.3,
    "momentum": 0.45,
    "wyckoff": 0.25
  }
}
```

**用户看到（输出层渲染）：**
```
📍 决策：止跌确认才试，最多5%仓位
   └─ 缠论底背驰(50%) + 动量中性 + 威科夫无信号
      加权: 0.18 | 大盘: 正常
```

### 冲突场景：缠论看多 vs 动量看空

```json
{
  "disagreement": 2,
  "action": "多方主导但有分歧，等转强"
}
```

触发降级：即使加权偏向多方，但因为分歧>1，自动降档。

---

## 六、扩展性：如何加新模块

注册一个新信号模块 = 两步：

**第1步：在 `merge_decisions()` 的参数列表中加一个信号函数调用：**
```python
def merge_decisions(chan_result, momentum_result, wyckoff_result, 
                    new_signal_result=None, regime="正常"):
```

**第2步：在 `REGIME_WEIGHTS` 的权重矩阵中加一行，在加权计算中加一项。**

**零修改任何现有分析模块。新模块只需要输出符合统一格式的 dict。**

---

## 七、边界与错误处理

| 场景 | 处理方式 |
|------|---------|
| 某分析模块返回空 dict | 对应信号 direction=0, confidence=0.2 |
| 信号函数抛出异常 | try/except → 该信号 direction=0, confidence=0 |
| 大盘数据不足 | 默认 regime="正常"，日志警告 |
| 权重和不为1 | assert 或 normalize |
| 所有信号都为空 | action="数据不足，观望" |

---

## 八、与现有代码的对接

### 8.1 在哪里注入

在 `build_report()` 之后、`render_markdown()` 之前插入融合调用。

```python
# 调用位置（在 trader / pool / portfolio 的 build_report 中）
# 现有代码（不改）：
chan_result = chanlun_strategy(current, bars, change_pct, quote)
momentum_result = momentum_strategy(current, bars, change_pct, quote)  
wyckoff_result = wyckoff_strategy(current, bars, change_pct, quote)

# === 新增：融合层 ===
from fusion_core import merge_decisions
from trader_shared.scripts.market_env import get_env_for_skill

env = get_env_for_skill("trader")
fusion = merge_decisions(
    chan_result=chan_result,
    momentum_result=momentum_result,
    wyckoff_result=wyckoff_result,
    regime=env.get("level", "正常"),
)

# 融合结果直接加到 report dict
report["fusion"] = fusion
```

### 8.2 渲染层（不动核心逻辑，只加展示字段）

在 `render_markdown()` 的输出模板中，fusion 结果是可选的：
- 有 fusion → 在决策段展示溯源信息
- 无 fusion → 只显示现有的 status/action 结果

**渲染层的改动很小：在 `📍 决策` 段后面加一个缩进行显示信号溯源。**

### 8.3 validate_output.py

需要更新 `schema/v1.py` 中的验证规则，让 fusion 字段可选：
- fusion 不在禁止字段列表中
- fusion 的存在不改变现有格式检查

---

## 九、调参与后续迭代

### 启动方式（第一版安全模式）

第一版默认 **只打日志，不改决策**。通过环境变量控制：

```python
import os

def merge_decisions(..., **kwargs) -> dict:
    log_only = os.environ.get("FUSION_LOG_ONLY", "true").lower() == "true"
    
    result = _do_merge(...)
    
    # 详细日志（每个调用都记录）
    import json
    print("FUSION:", json.dumps({
        "action": result["action"],
        "disagreement": result["disagreement"],
        "weighted_score": result["weighted_score"],
        "signals": {k: v["direction"] for k, v in result["signals_detail"].items()},
        "regime": result["regime"],
        "by_fusion": result["action"],    # 实际用的决策
    }, ensure_ascii=False))
    
    if log_only:
        # 安全模式：用现有 status_for() 的输出，不覆盖
        result["action"] = "日志模式，决策由现有系统输出（见 FUSION 日志）"
    
    return result
```

**启用正式融合决策：**
```bash
FUSION_LOG_ONLY=false python3 scripts/final_report.py --target 南网科技
```

**默认行为：安全模式，不动任何东西。** 等你看几组日志觉得对了，再关环境变量。

### 权重矩阵调参

权重矩阵后续迁移到 `fusion_weights.yml` 实现无代码可调。初始值：

```python
REGIME_WEIGHTS = {
    "正常": {"chan": 0.3, "momentum": 0.45, "wyckoff": 0.25},
    "偏弱": {"chan": 0.5, "momentum": 0.15, "wyckoff": 0.35},
    "很差": {"chan": 0.0, "momentum": 0.0, "wyckoff": 0.0},
}
```

**调参原则：** 先观察 1-2 周日志，看融合决策 vs 实际结果的对齐度，再调整。不要一上来就动权重，先跑对比数据。

### 后续迭代

```python
# Regime 权重
REGIME_WEIGHTS = {
    "正常": {"chan": 0.3, "momentum": 0.45, "wyckoff": 0.25},
    "偏弱": {"chan": 0.5, "momentum": 0.15, "wyckoff": 0.35},
    "很差": {"chan": 0.0, "momentum": 0.0, "wyckoff": 0.0},
}

# 冲突阈值
DISAGREEMENT_THRESHOLD = 2  # max(signals)-min(signals) > 2 触发降级（完全相反才降级，避免对中性信号过度敏感）

# 决策映射阈值（加权分数区间）
ACTION_MAP = {
    "正常": [
        (0.4, "半仓试（多方主导）"),
        (0.1, "增持"),
        (-0.05, "持股观望"),
        (-0.2, "减仓"),
        (-0.4, "空仓/止损"),
    ],
}
```

这些数据未来可迁移到 YAML 配置中，无需改代码。

---

## 十、代码行数估算

| 文件 | 行数 | 说明 |
|------|------|------|
| `fusion_core.py` | ~200 | 信号标准化 + merge 核心 + 冲突检测 |
| `fusion_regime.py` | ~100 | 权重矩阵 + 决策映射 |
| 各 skill 集成调用 | ~5/每skill × 4 = 20 | build_report 中加3-5行 |
| 渲染层 | ~20 | 可选展示 fusion 溯源 |
| 校验层 | ~10 | 标记 fusion 可选字段 |
| **合计新增** | **~350** | 零修改现有逻辑 |

---

## 十一、风险清单

| 风险 | 影响 | 缓解 |
|------|------|------|
| 权重矩阵不准 | 输出偏差 | 第一版默认 `FUSION_LOG_ONLY=true` 只日志，不生效决策。跑 1-2 周数据再开启 |
| 冲突阈值过敏 | 频繁降级 | 阈值设为 2（完全相反才降级），日志收集后评估调整 |
| 信号映射丢失信息 | 决策不够精细 | 保留 raw_key，融合层可逐步增加信号维度 |
| 大盘状态变化导致频繁切换 | 震荡市权重跳跃 | Hysteresis 机制（连续2次才切换权重），v3 实现 |
| 输出字段超出 SKILL.md 格式约束 | 校验失败 | fusion 字段不进入禁止列表，渲染层按需展示 |

---

## 十二、演进路线（不是这次的，但提前规划）

| 阶段 | 内容 |
|------|------|
| v1 (本次) | 基础融合层：3信号加权 + 冲突检测 + Regime权重 |
| v2 | 权重数据驱动：权重矩阵迁移到 YAML，支持无代码调参 |
| v3 | Hysteresis：防止大盘状态跳动导致权重频繁切换 |
| v4 | 回测框架：对历史信号跑融合决策 vs 实际结果，自动调参 |
| v5 | 新信号源：板块热度/财报/资金流接入，零改动现有代码 |

---

## 附录A：现有信号函数输出结构参考

### chanlun_strategy() 输出：
```json
{
  "chanlun": {
    "strokes": [...],
    "zones": [...],
    "buy_points": [{"type": "一类买", "price": 28.5, "confidence": 3}],
    "trend_label": "回调段 | 拉升段 | 数据不足",
    "buy_point_text": "一类买",
    "divergence": {"top_divergence": false, "bottom_divergence": true}
  }
}
```

### momentum_strategy() 输出：
```json
{
  "momentum": {
    "score": 72,
    "direction": "bullish",
    "signals": ["MACD柱为正(偏多)", "ADX强趋势(上涨)"]
  }
}
```

### wyckoff_strategy() 输出：
```json
{
  "wyckoff": {
    "spring_signal": true,
    "spring_price": 27.8,
    "bullish_volume_divergence": false
  }
}
```

### market_env assess() 输出：
```json
{
  "level": "正常",
  "change_pct": 1.2,
  "ma5": 4820,
  "ma20": 4750
}
```

## 附录B：决策流程图

```
                    ┌──────────────┐
                    │  各分析模块   │
                    │  独立运行     │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ 信号标准化    │
                    │ dir/conf/reason│
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  Regime 权重  │
                    │ 正常/偏弱/很差 │
                    └──────┬───────┘
                           │
              ┌────────────▼────────────┐
              │   加权汇总 weighted_sum  │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  分歧检测  disagreement   │
              │  max(dir)-min(dir) > 1   │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  信号 → 动作映射表        │
              │  冲突时降档              │
              └────────────┬────────────┘
                           │
                    ┌──────▼───────┐
                    │  融合结果输出  │
                    │  action +     │
                    │  confidence +  │
                    │  signals_detail│
                    └──────────────┘
```
