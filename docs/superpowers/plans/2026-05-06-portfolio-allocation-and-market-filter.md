# Portfolio Scoring Allocation + Market Filter Implementation Plan

> **Goal:** Replace ATR-only fixed allocation with Score-proportional allocation + wire market filter into signal downgrade logic

**Architecture:** 新增 `allocate_weights()` 函数替代内联 `target_weight()`；新增 `climate_adjust()` 和 `portfolio_total_cap()` 实现大盘过滤；在 `build_portfolio()` 中串联调用链

**Files:** 4 个文件：`portfolio_run.py`（核心）、`final_portfolio.py`（集成）、`config.py`（常量）、`test_portfolio_allocation.py`（测试）

**Tech:** Python 3.10+, 无新依赖

---

### Task 1: 新增测试文件结构

**Files:**
- Create: `01-功能包-packages/04-仓位轮动-trader-portfolio/tests/test_portfolio_allocation.py`

- [ ] **Step 1: 创建测试骨架（所有测试先标记为 skip）**

```python
"""Portfolio allocation scoring + market filter tests.

Tests for:
- allocate_weights()  Score-based proportional allocation
- climate_adjust()  Market-level signal downgrade
- portfolio_total_cap()  Market-driven total cap
- integration with build_portfolio()
"""
import pytest

# All tests pending — will enable in Task 5


class TestClimateAdjust:
    @pytest.mark.skip(reason="Pending Task 2")
    def test_very_weak_downgrade_low_buy_watch(self):
        from portfolio_run import climate_adjust
        assert climate_adjust("低吸观察", "很差") == "防守观察"

    @pytest.mark.skip(reason="Pending Task 2")
    def test_very_weak_downgrade_wait_for_strength(self):
        from portfolio_run import climate_adjust
        assert climate_adjust("等转强", "很差") == "防守观察"

    @pytest.mark.skip(reason="Pending Task 2")
    def test_normal_no_change(self):
        from portfolio_run import climate_adjust
        assert climate_adjust("等转强", "正常") == "等转强"

    @pytest.mark.skip(reason="Pending Task 2")
    def test_empty_market_level_no_change(self):
        from portfolio_run import climate_adjust
        assert climate_adjust("低吸观察", "") == "低吸观察"

    @pytest.mark.skip(reason="Pending Task 2")
    def test_none_market_level_no_change(self):
        from portfolio_run import climate_adjust
        assert climate_adjust("低吸观察", None) == "低吸观察"


class TestPortfolioTotalCap:
    @pytest.mark.skip(reason="Pending Task 2")
    def test_normal_returns_default(self):
        from portfolio_run import DEFAULT_MAX_TOTAL, portfolio_total_cap
        assert portfolio_total_cap("正常", False) == DEFAULT_MAX_TOTAL

    @pytest.mark.skip(reason="Pending Task 2")
    def test_weak_returns_70(self):
        from portfolio_run import portfolio_total_cap
        assert portfolio_total_cap("偏弱", False) == 70

    @pytest.mark.skip(reason="Pending Task 2")
    def test_weak_high_atr_returns_60(self):
        from portfolio_run import portfolio_total_cap
        assert portfolio_total_cap("偏弱", True) == 60

    @pytest.mark.skip(reason="Pending Task 2")
    def test_very_weak_returns_60(self):
        from portfolio_run import portfolio_total_cap
        assert portfolio_total_cap("很差", True) == 60

    @pytest.mark.skip(reason="Pending Task 2")
    def test_empty_market_returns_default(self):
        from portfolio_run import DEFAULT_MAX_TOTAL, portfolio_total_cap
        assert portfolio_total_cap("", False) == DEFAULT_MAX_TOTAL
        assert portfolio_total_cap(None, False) == DEFAULT_MAX_TOTAL


class TestAllocateWeights:
    @pytest.mark.skip(reason="Pending Task 3")
    def test_two_stocks_score_proportional(self):
        """Score 85/60 → weight ~85:60 ratio"""
        from portfolio_run import allocate_weights, DEFAULT_MAX_TOTAL
        items = [
            {"name": "票A", "score": 85, "atr_cap": 10, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 60, "atr_cap": 7, "ok": True, "status": "防守观察"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert weights["票A"] + weights["票B"] == 17  # sum of atr_caps
        assert weights["票A"] > weights["票B"]  # higher score → more weight

    @pytest.mark.skip(reason="Pending Task 3")
    def test_three_stocks_score_proportional(self):
        """Score 90/70/50 with atr_cap 10/8/6 = 24 total"""
        from portfolio_run import allocate_weights, DEFAULT_MAX_TOTAL
        items = [
            {"name": "票A", "score": 90, "atr_cap": 10, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 70, "atr_cap": 8, "ok": True, "status": "等转强"},
            {"name": "票C", "score": 50, "atr_cap": 6, "ok": True, "status": "防守观察"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        total = sum(weights.values())
        assert total == 24  # sum of atr_caps
        assert weights["票A"] > weights["票B"] > weights["票C"]

    @pytest.mark.skip(reason="Pending Task 3")
    def test_atr_cap_hard_limit(self):
        """High score stock with low atr_cap gets capped"""
        from portfolio_run import allocate_weights, DEFAULT_MAX_TOTAL
        items = [
            {"name": "票A", "score": 90, "atr_cap": 3, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 60, "atr_cap": 10, "ok": True, "status": "防守观察"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert weights["票A"] == 3  # capped at atr_cap
        assert weights["票B"] == 10
        assert weights["票A"] + weights["票B"] == 13

    @pytest.mark.skip(reason="Pending Task 3")
    def test_total_cap_override_cuts_lowest_score(self):
        """When sum(atr_cap) > max_total, cut from lowest score first"""
        from portfolio_run import allocate_weights
        # atr_cap sum = 30 > max_total 80... wait that's fine.
        # Let's do: atr_cap sum = 70 > max_total 60
        items = [
            {"name": "票A", "score": 85, "atr_cap": 40, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 40, "atr_cap": 30, "ok": True, "status": "防守观察"},
        ]
        weights = allocate_weights(items, max_total=60)
        total = sum(weights.values())
        assert total == 60
        # Low scorer (票B) should be cut more
        assert weights["票B"] < 30

    @pytest.mark.skip(reason="Pending Task 3")
    def test_single_tradable_stock(self):
        """Only 1 tradable stock → gets all its atr_cap"""
        from portfolio_run import allocate_weights, DEFAULT_MAX_TOTAL
        items = [
            {"name": "票A", "score": 85, "atr_cap": 10, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 60, "atr_cap": 7, "ok": True, "status": "暂不碰"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert weights == {"票A": 10}

    @pytest.mark.skip(reason="Pending Task 3")
    def test_zero_scores_equal_allocation(self):
        """All scores 0 → equal split of alloc_pool"""
        from portfolio_run import allocate_weights, DEFAULT_MAX_TOTAL
        items = [
            {"name": "票A", "score": 0, "atr_cap": 10, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 0, "atr_cap": 10, "ok": True, "status": "防守观察"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert weights["票A"] == weights["票B"]
        assert weights["票A"] + weights["票B"] == 20

    @pytest.mark.skip(reason="Pending Task 3")
    def test_negative_scores_fallback_30(self):
        """Negative scores fallback to 30"""
        from portfolio_run import allocate_weights, DEFAULT_MAX_TOTAL
        items = [
            {"name": "票A", "score": -50, "atr_cap": 10, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 60, "atr_cap": 7, "ok": True, "status": "防守观察"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert weights["票A"] >= 1  # not zero
        assert weights["票A"] + weights["票B"] == sum(10, 7)

    @pytest.org.skip(reason="Pending Task 3")
    def test_none_score_fallback_30(self):
        """Missing score uses fallback 30"""
        from portfolio_run import allocate_weights, DEFAULT_MAX_TOTAL
        items = [
            {"name": "票A", "atr_cap": 10, "ok": True, "status": "低吸观察"},  # no score key
            {"name": "票B", "score": 60, "atr_cap": 7, "ok": True, "status": "防守观察"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert "票A" in weights
        assert weights["票A"] >= 1

    @pytest.mark.skip(reason="Pending Task 3")
    def test_no_tradable_returns_empty(self):
        """All stocks filtered out → empty dict"""
        from portfolio_run import allocate_weights
        items = [
            {"name": "票A", "score": 85, "atr_cap": 10, "ok": True, "status": "暂不碰"},
            {"name": "票B", "score": 60, "atr_cap": 7, "ok": False, "status": "数据失败"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert weights == {}

    @pytest.mark.skip(reason="Pending Task 3")
    def test_filter_by_ok_flag(self):
        """Items with ok=False are excluded"""
        from portfolio_run import allocate_weights, DEFAULT_MAX_TOTAL
        items = [
            {"name": "票A", "score": 85, "atr_cap": 10, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 60, "atr_cap": 7, "ok": False, "status": "低吸观察"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert "票B" not in weights
        assert "票A" in weights
```

- [ ] **Step 2: 运行确认所有测试 skip 通过**

```bash
cd "01-功能包-packages/04-仓位轮动-trader-portfolio"
python3 -m pytest tests/test_portfolio_allocation.py -v
```
Expected: All tests skipped with `pytest.skip` reason shown.

---

### Task 2: 实现 climate_adjust + portfolio_total_cap + config 常量

**Files:**
- Modify: `01-功能包-packages/04-仓位轮动-trader-portfolio/scripts/portfolio_run.py:1-40`

- [ ] **Step 1: 在文件头部（常量区）添加 MARKET_DRAINAGE 和 DEFAULT_MAX_TOTAL 引用**

在 `from config import ...` 行之后添加：

```python
# Market filter constants
MARKET_DRAINAGE = {
    ("很差", "低吸观察"): "防守观察",
    ("很差", "防守观察"): "防守观察",
    ("很差", "等转强"): "防守观察",
    ("偏弱", "等转强"): "低吸观察",
}


def climate_adjust(status: str, market_level: str | None) -> str:
    """根据大盘环境对个股状态做降级，不改原始 status，只返回调整后的状态。"""
    if not market_level or market_level in ("正常", "", "未知"):
        return status
    return MARKET_DRAINAGE.get((market_level, status), status)


def portfolio_total_cap(market_level: str | None, has_high_atr: bool) -> int:
    """根据大盘状态和高波动返回总仓上限。"""
    if not market_level or market_level in ("正常", "", "未知"):
        return DEFAULT_MAX_TOTAL
    if market_level == "很差":
        return 60
    if market_level == "偏弱" and has_high_atr:
        return 60
    if market_level == "偏弱":
        return 70
    return DEFAULT_MAX_TOTAL
```

- [ ] **Step 2: 更新 Task 1 中对应的 skip 标记为未跳过**

替换 `TestClimateAdjust` 和 `TestPortfolioTotalCap` 类的 `@pytest.mark.skip` 装饰器为无（或删除 `reason` 参数）。

- [ ] **Step 3: 运行测试**

```bash
python3 -m pytest tests/test_portfolio_allocation.py::TestClimateAdjust -v
python3 -m pytest tests/test_portfolio_allocation.py::TestPortfolioTotalCap -v
```
Expected: All 9 tests pass.

- [ ] **Step 4: Commit**

```bash
git add 01-功能包-packages/04-仓位轮动-trader-portfolio/scripts/portfolio_run.py
git add 01-功能包-packages/04-仓位轮动-trader-portfolio/tests/test_portfolio_allocation.py
git commit -m "feat(portfolio): add climate_adjust and portfolio_total_cap for market filter"
```

---

### Task 3: 实现 allocate_weights + build_roles 改造

**Files:**
- Modify: `01-功能包-packages/04-仓位轮动-trader-portfolio/scripts/portfolio_run.py:187-252`

- [ ] **Step 1: 在 `signal_summary_for_item` 函数之后（约行 162），新增 `allocate_weights()` 函数**

```python
def allocate_weights(
    sorted_items: list[dict[str, Any]],
    *,
    max_total: int = DEFAULT_MAX_TOTAL,
) -> dict[str, int]:
    """Score 占比分配主逻辑。
    
    过滤: adjusted_status (降级后) != 暂不碰/数据失败 AND ok=True
    ATR cap 提供单票硬上限
    Score 占比决定初步分配，总量回退时从低分票开始削减
    """
    tradable = [
        item for item in sorted_items
        if item.get("ok")
        and (item.get("adjusted_status") or item.get("status") or "")
        not in {"暂不碰", "数据失败"}
    ]
    if not tradable:
        return {}
    
    total_cap = sum(int(item.get("atr_cap") or 10) for item in tradable)
    
    # 注意：Score 计算也使用 adjusted_status 对应的 status 值
    # （降级后 score 不改变，但 status 决定是否被过滤）
    alloc_pool = min(total_cap, max_total)
    
    # 计算 scores: None/空/0/负数 都按保底 30 处理
    scores: list[float] = []
    for item in tradable:
        raw = item.get("score") or item.get("livermore_score")
        s = float(raw) if raw is not None and raw != "" else 30.0
        if s <= 0:
            s = 30.0
        scores.append(s)
    
    total_score = sum(scores)
    if total_score <= 0:
        # 极端情况: 所有分数无效，均分
        n = len(tradable)
        each = max(1, round(alloc_pool / n))
        return {item["name"]: each for item in tradable}
    
    # 按 Score 占比分配，约束 ATR cap
    weights: dict[str, int] = {}
    for item, score in zip(tradable, scores):
        weight = round(score / total_score * alloc_pool)
        atr_cap = int(item.get("atr_cap") or 10)
        weight = max(weight, 0)
        weight = min(weight, atr_cap)
        weights[item["name"]] = weight
    
    # 总量回退: 从低分票开始削减
    actual_total = sum(weights.values())
    if actual_total > max_total:
        excess = actual_total - max_total
        sorted_by_score = sorted(
            tradable,
            key=lambda i: float(i.get("score") or i.get("livermore_score") or 30),
        )
        for item in sorted_by_score:
            if excess <= 0:
                break
            name = item["name"]
            w = weights.get(name, 0)
            cut = min(w, excess)
            weights[name] = w - cut
            excess -= cut
    
    return weights
```

- [ ] **Step 2: 改造 `build_roles()` 函数**

将现有（行 187-211）的 weight 计算逻辑替换为调用 `allocate_weights()`：

```python
def build_roles(sorted_items: list[dict[str, Any]], *, max_total: int, main_cap: int) -> dict[str, Any]:
    # ★ 使用 adjusted_status（降级后）过滤 tradable，与 allocate_weights 保持一致
    tradable = [
        item for item in sorted_items
        if item.get("ok")
        and (item.get("adjusted_status") or item.get("status") or "")
        not in {"暂不碰", "数据失败"}
    ]
    roles = {
        "主仓": tradable[0] if len(tradable) >= 1 else None,
        "副仓": tradable[1] if len(tradable) >= 2 else None,
        "观察": tradable[2] if len(tradable) >= 3 else None,
    }
    
    # ★ 用 Score 占比分配替换旧的 target_weight 循环
    weights = allocate_weights(sorted_items, max_total=max_total)
    
    total = sum(weights.values())
    actual_cash = max(0, 100 - total)
    avoid = [
        item["name"]
        for item in sorted_items
        if not item.get("ok") or item.get("status") in {"暂不碰", "数据失败"}
    ]
    return {"roles": roles, "weights": weights, "avoid": avoid, "total": total, "cash": actual_cash}
```

- [ ] **Step 3: 更新 Task 1 中 `TestAllocateWeights` 的 skip 标记**

- [ ] **Step 4: 修复 Task 1 中的一个 typo**

`test_none_score_fallback_30` 中有一行 `@pytest.org.skip` → 应改为 `@pytest.mark.skip`

- [ ] **Step 5: 运行测试**

```bash
python3 -m pytest tests/test_portfolio_allocation.py::TestAllocateWeights -v
```
Expected: All 10 tests pass.

- [ ] **Step 6: Commit**

```bash
git add 01-功能包-packages/04-仓位轮动-trader-portfolio/scripts/portfolio_run.py
git commit -m "feat(portfolio): replace target_weight with score-proportional allocate_weights"
```

---

### Task 4: 集成 market filter 到 build_portfolio + _with_climate_adjusted

**Files:**
- Modify: `01-功能包-packages/04-仓位轮动-trader-portfolio/scripts/portfolio_run.py:670-690`

- [ ] **Step 1: 在模块级新增 `_with_climate_adjusted()` 辅助函数**（放在 `climate_adjust` 函数之后）

```python
def _with_climate_adjusted(
    sorted_items: list[dict[str, Any]],
    market_level: str,
) -> list[dict[str, Any]]:
    """对 items 浅拷贝并添加 adjusted_status 字段。原始 status 保留用于显示。"""
    result = []
    for item in sorted_items:
        adj = dict(item)
        orig = str(item.get("status") or "")
        adj["adjusted_status"] = climate_adjust(orig, market_level)
        result.append(adj)
    return result
```

- [ ] **Step 2: 修改 `build_portfolio()` 函数（行 670-690）**

```python
def build_portfolio(
    targets: list[str],
    *,
    max_total: int = DEFAULT_MAX_TOTAL,
    cash_floor: int = DEFAULT_CASH_FLOOR,
    main_cap: int = DEFAULT_MAIN_CAP,
) -> dict[str, Any]:
    valid_targets = [item.strip() for item in targets if isinstance(item, str) and item.strip()]
    if len(valid_targets) < 2:
        raise RuntimeError("轮动仓位计划至少需要两只股票")
    provider = get_provider()
    items = [analyze_target(target, provider, LOOKBACK_DAYS) for target in valid_targets]
    if not any(item.get("ok") for item in items):
        raise RuntimeError("所有股票数据都获取失败，无法做仓位计划")
    sorted_items = sort_candidates(items)
    
    # ★ 新增: 大盘环境 → 总仓上限 + 信号降级
    market_level = get_market_level() or "正常"
    has_high_atr = any(
        float(it.get("atr_ratio") or 0) >= 0.03
        for it in sorted_items
        if it.get("ok")
    )
    effective_max = portfolio_total_cap(market_level, has_high_atr)
    
    # ★ 信号降级: 对 sorted_items 添加 adjusted_status
    if market_level not in ("正常", "", "未知"):
        sorted_items = _with_climate_adjusted(sorted_items, market_level)
    
    # ★ 获取大盘提示文本（必须在 build_roles 前获取）
    market_note = get_market_note()
    
    plan = build_roles(sorted_items, max_total=effective_max, main_cap=main_cap)
    markdown = render_markdown(items, plan, sorted_items, market_level, market_note, max_total=max_total, cash_floor=cash_floor, main_cap=main_cap)
    
    # ★ market_level 透传到信号生成
    signal_summaries = build_signal_summaries(
        sorted_items,
        max_total=main_cap,
        max_single_move=10,
        market_level=market_level,
    )
    return {"items": items, "sorted": sorted_items, "plan": plan, "signal_summaries": signal_summaries, "portfolio_markdown": markdown}
```

- [ ] **Step 3: 运行全量测试**

```bash
python3 -m pytest tests/test_portfolio_allocation.py -v
```
Expected: All 24 tests pass.

- [ ] **Step 4: 运行 self_check 和现有测试**

```bash
python3 scripts/self_check.py
```

- [ ] **Step 5: Commit**

```bash
git add 01-功能包-packages/04-仓位轮动-trader-portfolio/scripts/portfolio_run.py
git commit -m "feat(portfolio): integrate market filter into build_portfolio with signal downgrade"
```

---

### Task 5: 集成 signal_state_for_item 使用 adjusted_status

**Files:**
- Modify: `01-功能包-packages/04-仓位轮动-trader-portfolio/scripts/portfolio_run.py:84-98`

- [ ] **Step 1: 改造 `signal_state_for_item()` 签名**

```python
def signal_state_for_item(
    item: dict[str, Any],
    *,
    market_level: str | None = None,
) -> tuple[str, str, str, str]:
    # ★ 优先用 adjusted_status，降级后用于信号判定
    if market_level and market_level not in ("正常", "", "未知"):
        adj = item.get("adjusted_status")
        if adj:
            status = adj
        else:
            status = str(item.get("status") or "")
    else:
        status = str(item.get("status") or "")
    # ... 其余逻辑不变 ...
```

- [ ] **Step 2: 改造 `build_signal_for_item()` 签名并透传 `market_level`**

```python
def build_signal_for_item(
    item: dict[str, Any],
    *,
    max_total: int,
    max_single_move: int,
    market_level: str | None = None,
) -> dict[str, Any]:
    signal_type, direction, action, confidence = signal_state_for_item(
        item, market_level=market_level
    )
    # ... 其余逻辑不变 ...
```

- [ ] **Step 3: 更新 `build_signal_summaries()` 签名**

```python
def build_signal_summaries(
    items: list[dict[str, Any]],
    *,
    max_total: int,
    max_single_move: int,
    market_level: str | None = None,
) -> list[dict[str, Any]]:
    return [
        build_signal_for_item(
            item,
            max_total=max_total,
            max_single_move=max_single_move,
            market_level=market_level,
        )
        for item in items
    ]
```

- [ ] **Step 3: 更新 `build_signal_summaries()` 调用**

```python
def build_signal_summaries(
    items: list[dict[str, Any]],
    *,
    max_total: int,
    max_single_move: int,
    market_level: str | None = None,
) -> list[dict[str, Any]]:
    return [
        build_signal_for_item(item, max_total=max_total, max_single_move=max_single_move, market_level=market_level)
        for item in items
    ]
```

- [ ] **Step 4: 更新 `build_portfolio()` 中的调用**

```python
signal_summaries = build_signal_summaries(
    sorted_items,
    max_total=main_cap,
    max_single_move=10,
    market_level=market_level,
)
```

- [ ] **Step 5: 添加测试 + 运行 + commit**

```bash
python3 -m pytest tests/test_portfolio_allocation.py -v
python3 scripts/self_check.py
git add 01-功能包-packages/04-仓位轮动-trader-portfolio/scripts/portfolio_run.py
git commit -m "feat(portfolio): use adjusted_status in signal_state_for_item for market-aware signals"
```

---

### Task 6: 端到端验证

**Files:**
- 无新文件，仅验证

- [ ] **Step 1: 单票分析不受影响**

```bash
cd "01-功能包-packages/01-单票分析-trader"
python3 scripts/self_check.py
```

- [ ] **Step 2: Portfolio 组合仓位验证（无网络，检查代码路径不报错）**

```bash
cd "01-功能包-packages/04-仓位轮动-trader-portfolio"
python3 -c "
from portfolio_run import allocate_weights, climate_adjust, portfolio_total_cap

# 分配逻辑测试
items = [
    {'name': 'A', 'score': 85, 'atr_cap': 10, 'ok': True, 'status': '低吸观察'},
    {'name': 'B', 'score': 60, 'atr_cap': 7, 'ok': True, 'status': '防守观察'},
]
w = allocate_weights(items)
print('Allocation:', w, 'Total:', sum(w.values()))
assert sum(w.values()) == 17, f'Expected 17, got {sum(w.values())}'
assert w['A'] > w['B'], f'A should get more than B: {w}'

# 气候调整
assert climate_adjust('低吸观察', '很差') == '防守观察'
assert climate_adjust('等转强', '正常') == '等转强'

# 总仓上限
assert portfolio_total_cap('正常', False) == 80
assert portfolio_total_cap('偏弱', True) == 60
assert portfolio_total_cap('很差', False) == 60

print('All inline checks passed!')
"
```

- [ ] **Step 3: 运行完整测试**

```bash
python3 -m pytest tests/test_portfolio_allocation.py -v --tb=short
```

- [ ] **Step 4: 运行 self_check**

```bash
python3 scripts/self_check.py
```

- [ ] **Step 5: 最终提交**

```bash
git add .
git commit -m "feat(portfolio): end-to-end validation of scoring allocation + market filter"
```

---

## 执行总结

| 任务 | 内容 | 预计耗时 |
|---|---|---|
| Task 1 | 测试骨架 + skip 标记 | 3 min |
| Task 2 | climate_adjust + portfolio_total_cap + 对应测试 | 5 min |
| Task 3 | allocate_weights + build_roles 改造 + 10 测试 | 10 min |
| Task 4 | build_portfolio 集成 market filter + _with_climate_adjusted | 8 min |
| Task 5 | signal_state_for_item 适配 adjusted_status | 5 min |
| Task 6 | 端到端验证 + 全量测试 | 5 min |
| **合计** | | **~36 min** |

## 风险与降级

1. **`get_market_level()` 返回空字符串** → 已处理：默认 `"正常"`，等价于无降级
2. **ImportError 时 `get_market_level()` 无操作** → 已处理：`"正常"` fallback，分配逻辑正常工作
3. **Score 缺失** → 已处理：保底 30，参与均分
4. **Snapshot 模式不受影响** → `build_snapshot_portfolio()` 不调用 `build_roles` 改造版本，仅 `build_portfolio()` 受影响
