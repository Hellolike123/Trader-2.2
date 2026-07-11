# report_core 渲染优化 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 优化 `render_short_midline` 渲染，补全已计算但未展示的数据（筹码/来源标注/盈亏比判定），删冗余行，让报告对交易员更可操作。

**Architecture:** 纯渲染层改动，只动 `report_core.py` 的 `render_short_midline` 函数 + 新增测试文件。不改数据层（fusion/structure/chip 等模块），不改 schema。数据字段已全部核实存在。

**Tech Stack:** Python 3.13, pytest, trader_shared 包

**测试 venv:** `/Users/like/.workbuddy/binaries/python/envs/default/bin/python`
**PYTHONPATH:** `02-共享模块-shared:01-功能包-packages/trader/scripts`

---

## 不做的改动（已决定）

| 原计划 # | 内容 | 不做原因 |
|---------|------|---------|
| 8 | 📌 改「明日策略」模板 | `this_week` 是 fusion 层有判断的策略，比「若高开/若低开」机械模板更值钱，保留 |
| 9 | T0 移位 + 三价位 | 中间价 `(买高+卖低)/2` 缺结构依据；移位破坏「决策→关键价→盈亏比→亮点→T0」叙事流 |

---

## 共享测试 fixture

所有 Task 共用一个 `_report()` mock，放在 `test_report_optimization.py` 顶部。每个 Task 往里追加测试函数。

```python
"""report_core 渲染优化测试。"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.report_core import render_short_midline  # noqa: E402


def _report() -> dict:
    """三花智控 002050 mock（基于 2026-07-12 真实数据）。"""
    return {
        "name": "三花智控", "symbol": "002050.SZ",
        "current": 43.20, "change_pct": 0.82,
        "short_term_momentum": "转弱",
        "market_env": {"level": "偏弱"},
        "ma_raw": {"ma5": 43.14, "ma10": 43.50, "ma20": 44.65, "ma250": 42.75},
        "volume_ratio": 1.0, "turnover_rate": 3.0,
        "major_stage": "蓄势",
        "conclusion": {
            "midline": "盘整偏空 · 暂缓跟踪",
            "stage_line": "蓄势",
            "execution": "现价不买 · 不追",
            "reason": "亏1.4/赚1.0，不划算",
            "this_week": "不追现价；回买点再谈",
            "conflict": "周线偏空，短线也不追",
            "wave_label": "回调见底 · 关注一类买｜底背驰",
            "wave_label_mid": "笔数不足 · 无法判断",
        },
        "discipline": {"suggested_pct_cap": 0, "invalidation": "收盘有效跌破MA20(44.65)且反抽站不回；或跌破止损 41.85"},
        "fusion": {
            "signals_detail": {
                "chan": {"reason": "一类买 (底背驰)", "direction": 1},
                "momentum": {"reason": "动量中性", "direction": 0},
                "vpf": {"reason": "平量（量比1.1，近3日-1.4%）", "direction": 0, "volume_ratio": 1.05},
            },
            "fund_flow_outflow_veto_msg": None,
        },
        "key_prices": {
            "stop_sell": 41.85,
            "buy_zone_low": 41.93, "buy_zone_high": 42.98, "buy_ref": 42.46,
            "short_sell_low": 43.63, "short_sell_high": 44.19,
            "swing_sell": 46.0, "far_sell": 60.03,
            "risk": 0.61, "reward_near": 1.73,
            "risk_chase": 1.35, "reward_chase": 0.99,
        },
        "mid_key_prices": {
            "line_life": "41.14 生命线（破则中线转弱）",
            "line_pullback": "41.14-46.69 回踩区（到了才谈低吸）",
            "line_resist": "56.00 压力（靠近只减不加）",
            "line_target": "68.82 目标（波段上看）",
            "life_line": 41.14, "resist": 56.00,
        },
        "chip_current_pct": 8.3,
        "chip_peaks": [
            {"price": 41.75, "volume": 551950, "support_level": "弱支撑"},
            {"price": 44.95, "volume": 2751987, "support_level": "强阻力"},
            {"price": 49.36, "volume": 576185, "support_level": "弱阻力"},
        ],
        "support_source": "MA5", "resistance_source": "MA10",
        "support": 42.46, "confirm": 43.63,
        "extend_sector": {},
        "daily_bars": _daily_bars(),
    }


def _daily_bars() -> list[dict]:
    """20 根日线，最高在 19 天前。"""
    bars = []
    for i in range(20):
        if i == 0:
            h = 49.36  # 最高在第一天（19 天前）
        else:
            h = 43.0 + i * 0.1
        bars.append({"date": f"2026-06-{i+10:02d}", "high": h, "low": 42.0, "close": 43.0 + i * 0.05})
    return bars
```

---

### Task 1: 盈亏比 ✓/✗ 判定 + 卖点区目标百分比

**Files:**
- Modify: `02-共享模块-shared/trader_shared/report_core.py:447-462`（line_buy / line_chase 渲染）
- Modify: `02-共享模块-shared/trader_shared/report_core.py:423-427`（卖点区渲染）
- Test: `02-共享模块-shared/tests/test_report_optimization.py`

**Step 1: 写失败测试**

追加到 `test_report_optimization.py`：

```python
def test_risk_reward_ratio_with_verdict():
    """盈亏比行带 ✓/✗ 判定符号。"""
    out = render_short_midline(_report())
    # 买：盈亏比 2.8:1 ✓（risk=0.61, reward=1.73 → 1.73/0.61≈2.8）
    assert "盈亏比 2.8:1 ✓ 值得关注" in out
    # 追：盈亏比 0.7:1 ✗（risk_chase=1.35, reward_chase=0.99 → 0.99/1.35≈0.7）
    assert "盈亏比 0.7:1 ✗ 不划算" in out


def test_sell_zone_with_target_pct():
    """卖点区行带目标百分比。"""
    out = render_short_midline(_report())
    # short_sell_high=44.19, current=43.20 → (44.19-43.20)/43.20*100≈2.3%
    assert "目标+2.3%" in out
```

**Step 2: 验证测试失败**

```bash
PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts \
/Users/like/.workbuddy/binaries/python/envs/default/bin/python -m pytest \
02-共享模块-shared/tests/test_report_optimization.py::test_risk_reward_ratio_with_verdict \
02-共享模块-shared/tests/test_report_optimization.py::test_sell_zone_with_target_pct -v
```
Expected: FAIL（当前输出无「盈亏比」「目标+2.3%」字样）

**Step 3: 实现**

`report_core.py` — 替换 line_buy / line_chase 渲染逻辑（约 447-462 行）：

```python
    # 盈亏比行（用 key_prices 的 risk/reward 计算比值 + 判定符号）
    _kp = r.get("key_prices") or {}
    _risk = float(_kp.get("risk") or 0)
    _rew = float(_kp.get("reward_near") or 0)
    _risk_chase = float(_kp.get("risk_chase") or 0)
    _rew_chase = float(_kp.get("reward_chase") or 0)

    line_buy = _kp.get("line_buy") or ""
    line_chase = _kp.get("line_chase") or ""

    if line_buy:
        lines.append(f"  {line_buy}")
    elif buy_ref and stop_sell and _risk > 0:
        _ratio = _rew / _risk if _risk > 0 else 0
        _verdict = "✓ 值得关注" if _ratio >= 2.0 else ("✗ 不划算" if _ratio < 1.0 else "△ 一般")
        lines.append(f"  {float(buy_ref):.2f} 买：亏约 {_risk:.1f} / 赚约 {_rew:.1f} → 盈亏比 {_ratio:.1f}:1 {_verdict}")

    if line_chase:
        lines.append(f"  {line_chase}")
    elif current > 0 and stop_sell and _risk_chase > 0:
        _ratio_c = _rew_chase / _risk_chase if _risk_chase > 0 else 0
        _verdict_c = "✓ 值得关注" if _ratio_c >= 2.0 else ("✗ 不划算" if _ratio_c < 1.0 else "△ 一般")
        lines.append(f"  {current:.2f} 追：亏约 {_risk_chase:.1f} / 赚约 {_rew_chase:.1f} → 盈亏比 {_ratio_c:.1f}:1 {_verdict_c}")
```

`report_core.py` — 卖点区渲染（约 423-427 行），在 action 里加目标百分比：

```python
    if short_low and short_high:
        _tgt_pct = ""
        if current > 0 and float(short_high) > current:
            _tgt_pct = f"，目标+{(float(short_high) - current) / current * 100:.1f}%"
        if float(short_low) == float(short_high):
            _price_items.append((float(short_low), "卖点区", f"分批减仓{_tgt_pct}"))
        else:
            _price_items.append((float(short_low) - 0.001, f"卖点区 {float(short_low):.2f}-{float(short_high):.2f}", f"分批减仓{_tgt_pct}"))
```

**Step 4: 验证测试通过**

运行 Step 2 命令。Expected: PASS

**Step 5: Commit**

```bash
git add 02-共享模块-shared/trader_shared/report_core.py 02-共享模块-shared/tests/test_report_optimization.py
git commit -m "feat(report): 盈亏比行加 ✓/✗ 判定 + 卖点区目标百分比"
```

---

### Task 2: 价格阶梯来源标注

**Files:**
- Modify: `02-共享模块-shared/trader_shared/report_core.py:402-427`（买点区/卖点区加来源）
- Test: `02-共享模块-shared/tests/test_report_optimization.py`

**Step 1: 写失败测试**

```python
def test_price_source_annotation():
    """买点区/卖点区带来源标注。"""
    out = render_short_midline(_report())
    assert "← MA5支撑" in out  # support_source=MA5
    assert "← MA10压力" in out  # resistance_source=MA10


def test_price_source_unknown_no_annotation():
    """来源为空时不加标注。"""
    r = _report()
    r["support_source"] = None
    r["resistance_source"] = None
    out = render_short_midline(r)
    assert "←" not in out or "← MA5" not in out
```

**Step 2: 验证失败**

```bash
PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts \
/Users/like/.workbuddy/binaries/python/envs/default/bin/python -m pytest \
02-共享模块-shared/tests/test_report_optimization.py::test_price_source_annotation -v
```
Expected: FAIL

**Step 3: 实现**

`report_core.py` — 在买点区/卖点区 price_items 构造时加来源后缀：

```python
    _sup_src = str(r.get("support_source") or "").strip()
    _res_src = str(r.get("resistance_source") or "").strip()
    _SRC_MAP = {
        "low_5d": "近5日低点", "low_20d": "近20日低点",
        "ma5": "MA5支撑", "ma10": "MA10支撑", "ma20": "MA20支撑",
        "chip_support": "筹码密集区", "chip_resistance": "筹码密集区",
        "high_5d": "近5日高点", "high_20d": "近20日高点",
        "pivot_61.8": "黄金分割位",
    }
    _sup_label = _SRC_MAP.get(_sup_src.lower(), "")
    _res_label = _SRC_MAP.get(_res_src.lower(), "")

    if buy_low and buy_high:
        _src_suffix = f" ← {_sup_label}" if _sup_label else ""
        _price_items.append((float(buy_low) - 0.001, f"买点区 {float(buy_low):.2f}-{float(buy_high):.2f}", f"分批建仓{_src_suffix}"))
    elif buy_ref:
        _src_suffix = f" ← {_sup_label}" if _sup_label else ""
        _price_items.append((float(buy_ref), "买点区", f"分批建仓{_src_suffix}"))
```

卖点区同理，在 action 末尾加 `← {_res_label}`（与 Task 1 的目标百分比拼接）。

**Step 4: 验证通过**

运行 Step 2 命令。Expected: PASS

**Step 5: Commit**

```bash
git add 02-共享模块-shared/trader_shared/report_core.py 02-共享模块-shared/tests/test_report_optimization.py
git commit -m "feat(report): 价格阶梯加来源标注 ← MA5支撑/MA10压力"
```

---

### Task 3: 删除「说明」行

**Files:**
- Modify: `02-共享模块-shared/trader_shared/report_core.py:464-466`
- Test: `02-共享模块-shared/tests/test_report_optimization.py`

**Step 1: 写失败测试**

```python
def test_no_conflict_line():
    """删除「说明：{conflict}」行。"""
    r = _report()
    r["conclusion"]["conflict"] = "周线偏空，短线也不追"
    out = render_short_midline(r)
    assert "说明：周线偏空" not in out
```

**Step 2: 验证失败**

```bash
... -m pytest ...::test_no_conflict_line -v
```
Expected: FAIL（当前输出含「说明：周线偏空，短线也不追」）

**Step 3: 实现**

`report_core.py:464-466` — 删除 conflict 渲染块：

```python
    # 删除：说明行与出手行语义重复
    # if conflict:
    #     lines.append("")
    #     lines.append(f"说明：{conflict}")
```

**Step 4: 验证通过**

运行 Step 2。Expected: PASS

**Step 5: Commit**

```bash
git add ...
git commit -m "refactor(report): 删除冗余「说明」行（与出手行重复）"
```

---

### Task 4: ✅/⚠️ 区用具体数据替换模板文案

**Files:**
- Modify: `02-共享模块-shared/trader_shared/report_core.py:468-510`
- Test: `02-共享模块-shared/tests/test_report_optimization.py`

**Step 1: 写失败测试**

```python
def test_highlight_risk_specific():
    """亮点/风险用具体数据，不用模板空话。"""
    out = render_short_midline(_report())
    # 亮点应含缠论信号或阶段，不含「先看关键价与出手，不单看远支撑」空话
    assert "先看关键价与出手" not in out
    # 风险应含具体价位（MA20/止损），不只「等回买点」
    assert "41.85" in out  # 止损价
    assert "44.65" in out  # MA20 压力


def test_risk_uses_short_resist_not_mid():
    """风险行用短线 MA20 压力，不用中线远压力 56.00。"""
    out = render_short_midline(_report())
    # 当 execution 含「不追」时，风险应标 MA20 不是 56.00
    assert "上方MA20(44.65)压力" in out or "止损看 41.85" in out
```

**Step 2: 验证失败**

```bash
... -m pytest ...::test_highlight_risk_specific ...::test_risk_uses_short_resist_not_mid -v
```
Expected: FAIL

**Step 3: 实现**

`report_core.py:468-510` — 重写亮点/风险逻辑，优先用缠论信号 + 短线压力：

```python
    # ── 亮点 / 风险（具体数据驱动，禁模板空话）──
    _chan_sig = str((fusion_signals.get("chan") or {}).get("reason") or "")
    _ma20_v = _ma_float("ma20")
    _stop_v = float(stop_sell or 0)

    # 亮点：缠论信号 + 阶段 + MA5 上方
    _hl_parts = []
    if _chan_sig and _chan_sig != "无信号":
        _hl_parts.append(f"缠论{_chan_sig}")
    if stage_line and any(k in stage_line for k in ("蓄势", "主升")):
        _hl_parts.append(f"中线阶段{stage_line}")
    _ma5_v = _ma_float("ma5")
    if _ma5_v and current > 0 and current > _ma5_v:
        _hl_parts.append(f"现价在MA5上方")
    if _hl_parts:
        lines.append(f"✅ 亮点：{'；'.join(_hl_parts)}")
    elif "可跟踪" in mid or "未坏" in mid:
        lines.append(f"✅ 亮点：中线结构可跟踪" + (f"；阶段 {stage_line}" if stage_line else ""))
    else:
        lines.append(f"✅ 亮点：阶段 {stage_line or '未知'}，等短线信号" if stage_line else "✅ 亮点：等短线买点确认")

    # 风险：止损价 + 短线 MA20 压力（不用中线远压力 56.00）
    if "不追" in execution or "不买" in execution:
        _risk_parts = ["现价不宜追"]
        if _stop_v > 0:
            _risk_parts.append(f"止损看 {_stop_v:.2f}")
        if _ma20_v and _ma20_v > current > 0:
            _risk_parts.append(f"上方MA20({_ma20_v:.2f})压力")
        lines.append(f"⚠️ 风险：{'；'.join(_risk_parts)}")
    elif stage_line and "派发" in stage_line:
        lines.append(f"⚠️ 风险：派发阶段注意破位" + (f"，跌破 {_stop_v:.2f} 需离场" if _stop_v else ""))
    elif stage_line and "衰退" in stage_line:
        lines.append("⚠️ 风险：衰退阶段，不宜介入")
    elif life_v > 0 and current > 0 and current < life_v * 1.02:
        lines.append(f"⚠️ 风险：靠近/跌破中线生命线 {life_v:.2f}")
    else:
        lines.append("⚠️ 风险：未站稳前不提前加仓")
```

**Step 4: 验证通过**

运行 Step 2。Expected: PASS

**Step 5: Commit**

```bash
git add ...
git commit -m "feat(report): 亮点/风险用具体数据替换模板文案"
```

---

### Task 5: 中线筹码状态行

**Files:**
- Modify: `02-共享模块-shared/trader_shared/report_core.py:229`（缠论行后插入）
- Test: `02-共享模块-shared/tests/test_report_optimization.py`

**Step 1: 写失败测试**

```python
def test_midline_chip_status():
    """中线区有筹码状态行：获利盘 + 套牢峰。"""
    out = render_short_midline(_report())
    assert "筹码：获利盘 8.3%" in out
    assert "套牢峰 44.95" in out  # current(43.20) 以上最近的峰


def test_midline_chip_no_above_peak_graceful():
    """无上方峰时不显示筹码行（不报错）。"""
    r = _report()
    r["chip_peaks"] = [{"price": 40.0, "volume": 100, "support_level": "弱支撑"}]
    r["chip_current_pct"] = 95.0
    out = render_short_midline(r)
    assert "套牢峰" not in out  # 无上方峰不显示套牢


def test_midline_chip_missing_graceful():
    """筹码数据缺失时不显示筹码行。"""
    r = _report()
    r["chip_peaks"] = []
    r["chip_current_pct"] = None
    out = render_short_midline(r)
    assert "筹码：" not in out
```

**Step 2: 验证失败**

```bash
... -m pytest ...::test_midline_chip_status -v
```
Expected: FAIL

**Step 3: 实现**

`report_core.py` — 在缠论行（约 229 行）之后插入筹码行：

```python
    lines.append(f"  缠论：{_chan_display}")

    # 筹码状态行（获利盘 + 上方套牢峰）
    _chip_pct = r.get("chip_current_pct")
    _chip_peaks = r.get("chip_peaks") or []
    _above_peaks = [p for p in _chip_peaks if isinstance(p, dict) and float(p.get("price") or 0) > current] if current > 0 else []
    _chip_parts = []
    if _chip_pct is not None and isinstance(_chip_pct, (int, float)):
        _chip_parts.append(f"获利盘 {_chip_pct:.1f}%")
    if _above_peaks:
        _above_peaks.sort(key=lambda x: float(x.get("price") or 0))
        _nearest = _above_peaks[0]
        _peak_price = float(_nearest.get("price") or 0)
        _tag = "上方压力重" if _peak_price < current * 1.10 else "上方有压力"
        _chip_parts.append(f"套牢峰 {_peak_price:.2f}（{_tag}）")
    if _chip_parts:
        lines.append(f"  筹码：{' ｜ '.join(_chip_parts)}")
```

**Step 4: 验证通过**

运行 Step 2 + 其他两个测试。Expected: PASS

**Step 5: Commit**

```bash
git add ...
git commit -m "feat(report): 中线区增加筹码状态行（获利盘+套牢峰）"
```

---

### Task 6: 动能行展示 reason 原文

**Files:**
- Modify: `02-共享模块-shared/trader_shared/report_core.py:342-351`
- Test: `02-共享模块-shared/tests/test_report_optimization.py`

**Step 1: 写失败测试**

```python
def test_momentum_reason_full():
    """动能行展示 reason 原文，不截断不编造。"""
    r = _report()
    r["fusion"]["signals_detail"]["momentum"]["reason"] = "MACD柱缩短（多头衰减）"
    out = render_short_midline(r)
    assert "动能：MACD柱缩短（多头衰减）" in out
    # 不应被截断
    assert "动能：MACD柱缩短（多头衰减）" == [l.strip() for l in out.split("\n") if l.strip().startswith("动能：")][0]


def test_momentum_short_reason():
    """短 reason 保持原样。"""
    r = _report()
    r["fusion"]["signals_detail"]["momentum"]["reason"] = "动量中性"
    out = render_short_midline(r)
    assert "动能：动量中性" in out
```

**Step 2: 验证失败**

```bash
... -m pytest ...::test_momentum_reason_full -v
```
Expected: 可能 FAIL（当前代码会去掉括号内容并截断 25 字）

**Step 3: 实现**

`report_core.py:342-351` — 去掉括号删除和 25 字截断，展示原文（仅超长时截断到 40 字）：

```python
    # 动能（展示 reason 原文，不删括号不编造分项）
    _msig = fusion_signals.get("momentum") if isinstance(fusion_signals.get("momentum"), dict) else {}
    if _msig:
        _mst = str(_msig.get("reason") or "").replace("动量", "").replace("动能", "").strip().lstrip(":：").strip() or "无信号"
        # 不再删括号内容；仅超长时截断
        if len(_mst) > 40:
            _mst = _mst[:38] + "…"
        lines.append(f"  动能：{_mst}")
    else:
        lines.append("  动能：暂无信号")
```

**Step 4: 验证通过**

运行 Step 2。Expected: PASS

**Step 5: Commit**

```bash
git add ...
git commit -m "fix(report): 动能行展示 reason 原文不截断不删括号"
```

---

### Task 7: 价量资金展示 vpf.reason 原文

**Files:**
- Modify: `02-共享模块-shared/trader_shared/report_core.py:353-362`
- Test: `02-共享模块-shared/tests/test_report_optimization.py`

**Step 1: 写失败测试**

```python
def test_vpf_reason_full():
    """价量资金行展示 vpf.reason 原文（含量比和近3日涨跌）。"""
    out = render_short_midline(_report())
    assert "价量资金：平量（量比1.1，近3日-1.4%）" in out


def test_vpf_no_fund_flow_veto_no_append():
    """无 fund_flow_outflow_veto_msg 时不追加资金流向。"""
    r = _report()
    r["fusion"]["fund_flow_outflow_veto_msg"] = None
    out = render_short_midline(r)
    assert "主力" not in out.split("价量资金")[1].split("\n")[0] if "价量资金" in out else True


def test_vpf_with_veto_appends():
    """有 fund_flow_outflow_veto_msg 时追加到价量资金行。"""
    r = _report()
    r["fusion"]["fund_flow_outflow_veto_msg"] = "连续 3 日主力净流出超阈值"
    out = render_short_midline(r)
    assert "主力连续 3 日净流出" in out or "连续 3 日主力净流出" in out
```

**Step 2: 验证失败**

```bash
... -m pytest ...::test_vpf_reason_full ...::test_vpf_with_veto_appends -v
```
Expected: FAIL

**Step 3: 实现**

`report_core.py:353-362` — 展示完整 reason，有 veto 时追加：

```python
    # 价量资金（展示 reason 原文 + 资金否决追加）
    _vsig = fusion_signals.get("vpf") if isinstance(fusion_signals.get("vpf"), dict) else {}
    if _vsig:
        _vst = str(_vsig.get("reason") or _vsig.get("vp_reason") or "").strip() or "中性"
        # 不删括号；仅超长截断
        if len(_vst) > 40:
            _vst = _vst[:38] + "…"
        # 有资金否决时追加（veto_msg 格式："连续 N 日主力净流出超阈值"）
        _veto = str(fusion.get("fund_flow_outflow_veto_msg") or "").strip()
        if _veto:
            # 提取天数，简化为「主力连续N日净流出」
            import re as _re
            _days_m = _re.search(r"连续\s*(\d+)\s*日", _veto)
            if _days_m:
                _vst = f"{_vst} ｜ 主力连续{_days_m.group(1)}日净流出"
            else:
                _vst = f"{_vst} ｜ {_veto}"
        lines.append(f"  价量资金：{_vst}")
    else:
        lines.append("  价量资金：暂无信号")
```

**Step 4: 验证通过**

运行 Step 2 全部 3 个测试。Expected: PASS

**Step 5: Commit**

```bash
git add ...
git commit -m "feat(report): 价量资金展示 reason 原文 + 资金否决追加"
```

---

### Task 8: 调整天数 + 相对强弱降级

**Files:**
- Modify: `02-共享模块-shared/trader_shared/report_core.py:119-128`（量比换手行后追加）
- Test: `02-共享模块-shared/tests/test_report_optimization.py`

**Step 1: 写失败测试**

```python
def test_adjust_days():
    """meta 区显示调整天数。"""
    out = render_short_midline(_report())
    assert "调整：第19天" in out


def test_adjust_days_new_high():
    """创新高时显示「创新高」不显示天数。"""
    r = _report()
    # 把最后一根 bar 的 high 设成最高 → 距离 0 天
    r["daily_bars"][-1]["high"] = 50.0
    out = render_short_midline(r)
    assert "创新高" in out or "第0天" not in out


def test_relative_strength_when_sector_empty():
    """extend_sector 为空时不显示相对强弱行。"""
    r = _report()
    r["extend_sector"] = {}
    out = render_short_midline(r)
    assert "相对强弱" not in out


def test_relative_strength_when_sector_present():
    """extend_sector 有数据时显示相对强弱。"""
    r = _report()
    r["extend_sector"] = {"status": "正常", "stock_vs_sector": "跑赢 +1.50%"}
    out = render_short_midline(r)
    assert "相对强弱：跑赢 +1.50%" in out
```

**Step 2: 验证失败**

```bash
... -m pytest ...::test_adjust_days ...::test_relative_strength_when_sector_present -v
```
Expected: FAIL

**Step 3: 实现**

`report_core.py` — 在量比换手行（约 128 行）之后插入调整天数 + 相对强弱：

```python
    if vol_parts:
        lines.append(f"  {' ｜ '.join(vol_parts)}")

    # 调整天数（距近 20 日最高点的天数）
    _bars = r.get("daily_bars") or []
    if len(_bars) >= 20 and current > 0:
        _recent = _bars[-20:]
        _highs = [(i, float(b.get("high") or 0)) for i, b in enumerate(_recent) if float(b.get("high") or 0) > 0]
        if _highs:
            _max_i, _max_h = max(_highs, key=lambda x: x[1])
            _days_from_high = len(_recent) - 1 - _max_i
            if _days_from_high == 0:
                lines.append(f"  创新高（近20日）")
            else:
                lines.append(f"  调整：第{_days_from_high}天")

    # 相对强弱（仅 extend_sector 有数据时显示）
    _ext_sec = r.get("extend_sector") or {}
    if isinstance(_ext_sec, dict) and _ext_sec.get("status") == "正常":
        _vs = str(_ext_sec.get("stock_vs_sector") or "").strip()
        if _vs:
            lines.append(f"  相对强弱：{_vs}")
```

**Step 4: 验证通过**

运行全部 4 个测试。Expected: PASS

**Step 5: Commit**

```bash
git add ...
git commit -m "feat(report): meta 区加调整天数+相对强弱（extend_sector 空时降级）"
```

---

### Task 9: 中线关键价格式统一

**Files:**
- Modify: `02-共享模块-shared/trader_shared/mid_key_prices.py`（line_life/line_pullback/line_resist/line_target 格式）
- Test: `02-共享模块-shared/tests/test_report_optimization.py`

**Step 1: 写失败测试**

```python
def test_mid_key_price_format():
    """中线关键价格式：价格前置 + 动作统一。"""
    out = render_short_midline(_report())
    # 生命线：41.14 生命线（跌破则减仓）
    assert "41.14 生命线" in out
    # 回踩区：41.14-46.69 回踩区（到了分批低吸）
    assert "41.14-46.69 回踩区" in out
    # 压力位：56.00 压力位（靠近分批减仓）
    assert "56.00 压力位" in out or "56.00 压力" in out
    # 目标位：68.82 目标位（到了分批止盈）
    assert "68.82 目标位" in out or "68.82 目标" in out
```

**Step 2: 验证失败**

```bash
... -m pytest ...::test_mid_key_price_format -v
```
Expected: FAIL（当前格式是「生命线 41.14（破则中线转弱）」名字前置）

**Step 3: 实现**

改 `mid_key_prices.py` 的 `build_mid_key_prices` 输出格式，把价格前置、动作统一：

- `生命线 41.14（破则中线转弱）` → `41.14 生命线（跌破则减仓）`
- `回踩区 41.14-46.69（到了才谈低吸）` → `41.14-46.69 回踩区（到了分批低吸）`
- `压力 56.00（靠近只减不加）` → `56.00 压力位（靠近分批减仓）`
- `目标 68.82（波段上看）` → `68.82 目标位（到了分批止盈）`

（具体改动在 `mid_key_prices.py` 的格式化函数里，实施时定位精确行号。）

**Step 4: 验证通过**

运行 Step 2 + 跑 `test_report_mid_short_sources.py` 确认无回归。

```bash
PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts \
/Users/like/.workbuddy/binaries/python/envs/default/bin/python -m pytest \
02-共享模块-shared/tests/test_report_mid_short_sources.py -v
```
Expected: PASS（注意：test_contract.py 有 3 项既有失败，不属于本任务范围）

**Step 5: Commit**

```bash
git add ...
git commit -m "style(report): 中线关键价格式统一（价格前置+动作统一）"
```

---

## 最终验证

**Step 1: 跑全部新测试**

```bash
PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts \
/Users/like/.workbuddy/binaries/python/envs/default/bin/python -m pytest \
02-共享模块-shared/tests/test_report_optimization.py -v
```
Expected: 全部 PASS

**Step 2: 跑现有测试确认无回归**

```bash
PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts \
/Users/like/.workbuddy/binaries/python/envs/default/bin/python -m pytest \
02-共享模块-shared/tests/test_report_mid_short_sources.py -v
```
Expected: PASS

**Step 3: 实跑 002050 对比输出**

```bash
PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts \
/Users/like/.workbuddy/binaries/python/envs/default/bin/python \
01-功能包-packages/trader/scripts/final_report.py --target 002050 --output markdown
```
Expected: 输出与修正版 Mockup 一致（筹码行/来源标注/盈亏比 ✓✗/目标%/调整天数 均出现，说明行消失）

**Step 4: 跑第二只票验证泛化**

```bash
... final_report.py --target 600519 --output markdown
```
Expected: 无报错，无空行降级正常

---

## 执行顺序依赖

```
Task 1（盈亏比+目标%）→ 无依赖
Task 2（来源标注）→ 依赖 Task 1 的卖点区改动
Task 3（删说明行）→ 无依赖
Task 4（亮点风险）→ 无依赖
Task 5（筹码行）→ 无依赖
Task 6（动能 reason）→ 无依赖
Task 7（价量资金 reason）→ 无依赖
Task 8（调整天数）→ 无依赖
Task 9（中线关键价格式）→ 无依赖

建议顺序：1→2→3→4→5→6→7→8→9（按报告从上到下区域顺序）
```

Task 1-8 互相独立，可并行。Task 2 依赖 Task 1 的卖点区行改动（目标百分比 + 来源标注拼接）。
