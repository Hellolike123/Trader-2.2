# 2026-05-06 — Portfolio Allocation Scoring + Market Filter Design

## 1. 业务问题

当前组合仓位分配存在两个明确缺口：

1. **每票仓位固定化**：`target_weight()` 公式是 `bw * scale / max(scale, 0.01)`（portfolio_run.py:181），`scale` 被消掉后始终等于 `base_weight`（仅由 ATR 决定），pyramid tier 对仓位毫无影响。主/副/观察只是排序位置硬切，没有真正的组合比例设计。
2. **大盘环境不生效**：`get_market_level()` 能判断大盘"正常/偏弱/很差"（pipeline.py:149），但只体现在 Markdown 文本里，不进入 `build_portfolio()` 的分配流程。信号降级没有被实现。

## 2. 设计目标

- **Score 差异化仓位分配**：用 Score 在候选间的相对占比决定仓位分配，ATR Cap 仅提供单票上限
- **大盘环境过滤**：大盘偏弱/很差时自动降级信号，影响状态判定和仓位上限
- **最小侵入**：不改动 shared 模块核心分析管线，所有变更集中在 trader-portfolio skill
- **向后兼容**：现有 `build_roles()` 接口签名不变，返回格式不变，新增 `allocate_weights()` 函数

## 3. 方案：Score 占比 × ATR Cap

### 3.1 核心流程

```
步骤 1: 过滤 tradable
tradable = sorted_items 中 status 不是 "暂不碰"/"数据失败"/ok=False 的 item

步骤 2: 大盘环境决定总仓上限
effective_max = portfolio_total_cap(market_level, has_high_atr)

步骤 3: 计算可分配池
alloc_pool = min(sum(atr_cap for item in tradable), effective_max)

步骤 4: 按 Score 占比分配
total_score = sum(score for item in tradable)，零值保底为 30
单票权重 = round(score / total_score * alloc_pool)
实际仓位 = min(权重, atr_cap)

步骤 5: 总量回退切割
如果 actual_total > effective_max，按 score 从低到高依次削减直到实际 ≤ cap

步骤 6: 构建返回值
{"roles": {...}, "weights": {...}, "avoid": [...], "total": actual_total, "cash": 100 - actual_total}
```

### 3.2 举例

| 股票 | Score | ATR Cap | 占比 | 分配 |
|---|---|---|---|---|
| 南网科技 | 85 | 10 | 85/145=59% | min(10, round(59%×17)=10) → **10%** |
| 中国铝业 | 60 | 7 | 60/145=41% | min(7, round(41%×17)=7) → **7%** |
| **合计** | — | 17 | — | **17%**（≤80 总上限） |

### 3.3 新增函数 `allocate_weights()` (portfolio_run.py)

```python
def allocate_weights(
    sorted_items: list[dict[str, Any]],
    *,
    max_total: int = DEFAULT_MAX_TOTAL,
) -> dict[str, int]:
    """Score 占比分配主逻辑。
    
    过滤条件: status != 暂不碰/数据失败 AND ok=True
    ATR cap 提供单票硬上限
    Score 占比决定初步分配，总量回退时从低分票开始削减
    """
    # 步骤 1: 过滤 tradable（保持与 sort_candidates 一致的 ok 过滤）
    tradable = [
        item for item in sorted_items
        if item.get("ok")
        and item.get("status") not in {"暂不碰", "数据失败"}
    ]
    if not tradable:
        return {}
    
    # 步骤 2: 计算可分配池
    total_cap = sum(int(item.get("atr_cap") or 10) for item in tradable)
    alloc_pool = min(total_cap, max_total)
    
    # 步骤 3: 计算 total_score，零值/负值保底为 30
    scores: list[float] = []
    for item in tradable:
        raw = item.get("score") or item.get("livermore_score")
        s = float(raw) if raw is not None and raw != "" else 30.0
        if s <= 0:
            s = 30.0  # 分数无效时按基准分 30 处理
        scores.append(s)
    
    total_score = sum(scores)
    if total_score <= 0:
        # 极端情况：所有分数都为 0 或负数，均分
        n = len(tradable)
        each = max(1, round(alloc_pool / n))
        return {item["name"]: each for item in tradable}
    
    # 步骤 4: 按 Score 占比分配，约束 ATR cap
    weights: dict[str, int] = {}
    for item, score in zip(tradable, scores):
        weight = round(score / total_score * alloc_pool)
        atr_cap = int(item.get("atr_cap") or 10)
        weight = max(weight, 0)  # 保底 0
        weight = min(weight, atr_cap)  # ATR cap 硬约束
        weights[item["name"]] = weight
    
    # 步骤 5: 总量回退 — 从低分票开始削减
    actual_total = sum(weights.values())
    if actual_total > max_total:
        excess = actual_total - max_total
        # 按 score 升序排列（最低分先减）
        sorted_by_score = sorted(tradable, key=lambda i: float(i.get("score") or i.get("livermore_score") or 30))
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

**与现有 `target_weight()` 的对比**：

| 维度 | 现有 `target_weight()` | 新 `allocate_weights()` |
|---|---|---|
| 主因子 | ATR base_weight（单一） | Score 占比 + ATR cap |
| 组合感知 | 无，每票独立计算 | 有，可分配池全局限制 |
| 金字塔影响 | scale 被消掉无效 | 通过 score → weight 间接体现 |
| 排序影响 | 无 | 有，score 越高分配越多 |

### 3.4 `build_roles()` 改造

现有代码（portfolio_run.py:187-211）在 `build_roles()` 内用 `target_weight()` 计算 weights。改造后：

```python
def build_roles(sorted_items: list[dict[str, Any]], *, max_total: int, main_cap: int) -> dict[str, Any]:
    tradable = [item for item in sorted_items if item.get("ok") and item.get("status") not in {"暂不碰", "数据失败"}]
    roles = {
        "主仓": tradable[0] if len(tradable) >= 1 else None,
        "副仓": tradable[1] if len(tradable) >= 2 else None,
        "观察": tradable[2] if len(tradable) >= 3 else None,
    }
    
    # ★ 新: 用 Score 占比分配替换旧 target_weight 循环
    weights = allocate_weights(sorted_items, max_total=max_total)
    
    total = sum(weights.values())
    actual_cash = max(0, 100 - total)
    avoid = [item["name"] for item in sorted_items if not item.get("ok") or item.get("status") in {"暂不碰", "数据失败"}]
    return {"roles": roles, "weights": weights, "avoid": avoid, "total": total, "cash": actual_cash}
```

**不改动点**：
- 返回 dict 结构不变：`roles`, `weights`, `avoid`, `total`, `cash`
- `render_markdown()` 读取 `plan["weights"]` 的代码不用改
- `sort_candidates()` (`portfolio_core.py:125`) 排序逻辑不变
- 现有单票分析管线（`target_weight()`）保留供其他 skill 使用

### 3.5 边缘情况处理

| 场景 | 处理 |
|---|---|
| 只有 1 个 tradable（第 2 个是"暂不碰"） | 可分配池 = atr_cap(10)，alloc_pool = min(10, 80) = 10，score 占比 = 100%，权重 = 10 ✓ |
| score 全为 0 或负数 | 均分 alloc_pool，每票 `max(1, round(alloc_pool/n))` ✓ |
| 单票 Score × pool > atr_cap | `min(权重, atr_cap)` 约束 ✓ |
| actual_total > max_total | 从低分开始削减至 total ≤ max ✓ |
| `get_market_level()` 返回空字符串 | 默认走 `DEFAULT_MAX_TOTAL` 80%（见 §4.4） |

---

## 4. 大盘环境过滤（第二阶段）

### 4.1 信号降级规则

| 大盘状态 | 降级动作 | 影响 |
|---|---|---|
| **很差** | 低吸观察 → 防守观察；防守观察 → 防守观察；等转强 → 防守观察 | 状态降 1-2 级，仓位降低 |
| **偏弱** | 等转强 → 低吸观察 | 状态降 1 级 |

> 不修改原始 `item["status"]`，只返回 `adjusted_status` 用于 `allocate_weights` 和 `signal_state_for_item`。

### 4.2 降级函数

```python
MARKET_DRAINAGE = {  # (market_level, original_status) → adjusted_status
    ("很差", "低吸观察"): "防守观察",
    ("很差", "防守观察"): "防守观察",
    ("很差", "等转强"): "防守观察",
    ("偏弱", "等转强"): "低吸观察",
}

def climate_adjust(status: str, market_level: str, item: dict | None = None) -> str:
    """根据大盘环境对个股状态做降级，不改原始 item，只返回调整后的状态。"""
    if not market_level or market_level in ("正常", "", "未知"):
        return status
    return MARKET_DRAINAGE.get((market_level, status), status)
```

### 4.3 总仓上限联动

```python
def portfolio_total_cap(market_level: str, has_high_atr: bool) -> int:
    if not market_level or market_level in ("正常", "", "未知"):
        return DEFAULT_MAX_TOTAL  # 80
    if market_level == "很差":
        return 60
    if market_level == "偏弱" and has_high_atr:
        return 60
    if market_level == "偏弱":
        return 70
    return DEFAULT_MAX_TOTAL  # 兜底
```

### 4.4 `get_market_level()` 空值处理

现有 `trader_shared` 的 `get_market_level()` 在 ImportError 时返回空字符串 `""`（portfolio_run.py:35）。空字符串代表"数据不可用"，应默认走正常市场（不激进降级）。改造后的调用链应处理：`market_level or "正常"` 保证 fallback。

### 4.5 在 `build_portfolio()` 中的集成

现有代码（portfolio_run.py:670-690）：

```python
def build_portfolio(targets, *, max_total, cash_floor, main_cap):
    # ... fetch & analyze ...
    sorted_items = sort_candidates(items)
    
    # ★ 新: 获取大盘环境 + 计算调整后有效上限
    market_level = get_market_level() or "正常"
    has_high_atr = any(float(it.get("atr_ratio") or 0) >= 0.03 for it in sorted_items if it.get("ok"))
    effective_max = portfolio_total_cap(market_level, has_high_atr)
    
    # ★ 新: 如果大盘偏弱/很差，对 sorted_items 内创建 adjusted_status 副本
    if market_level not in ("正常", "", "未知"):
        sorted_items = _with_climate_adjusted(sorted_items, market_level)
    
    plan = build_roles(sorted_items, max_total=effective_max, main_cap=main_cap)
    # ... render & signals ...
```

新增辅助函数 `_with_climate_adjusted()`：

```python
def _with_climate_adjusted(sorted_items: list[dict], market_level: str) -> list[dict]:
    """对 items 增加 "adjusted_status" 字段，保留原始 status 用于显示。"""
    result = []
    for item in sorted_items:
        adj = dict(item)  # 浅拷贝
        orig = item.get("status", "")
        adj["adjusted_status"] = climate_adjust(orig, market_level, item)
        result.append(adj)
    return result
```

`allocate_weights()` 内部读取 `adjusted_status` 而非原始 `status` 过滤 tradable：

```python
# allocate_weights 内改动一行:
tradable = [
    item for item in sorted_items
    if item.get("ok")
    and item.get("adjusted_status")  # ★ 用降级后的状态过滤
    not in {"暂不碰", "数据失败"}
]
```

### 4.6 对 `signal_state_for_item()` 的影响

现有代码（portfolio_run.py:84-98）根据 `status` 判断 signal。改造后：

```python
def signal_state_for_item(
    item: dict[str, Any],
    *,
    market_level: str = "",
) -> tuple[str, str, str, str]:
    status = item.get("adjusted_status") or str(item.get("status") or "")  # ★ 优先用 adjusted_status
    # ... 其余逻辑不变 ...
```

### 4.7 对 `render_markdown()` 的影响

`render_markdown()` 已经根据 `market_level` 渲染文本警告（portfolio_run.py:534-536），这段不变。新增改动：

```python
# render_markdown 签名新增 market_level 参数（已有）
# 渲染操作建议时，用 adjusted_status 替代 status:
```

现有 `render_markdown()` 读取 `item.get("status")` 用于显示（portfolio_run.py:529）。保留原始 status 显示 + 用 adjusted_status 做逻辑判断，两者在输出中不混淆：显示用原始，决策用 adjusted。

---

## 5. 数据流

```
fetch_quote + daily  →  analyze_target()  →  status, score, atr_cap, atr_ratio
                                                         ↓
                                                sort_candidates()
                                                         ↓
                              get_market_level() ← market_env.assess() 或 trader_shared cache
                                                         ↓
                              ← has_high_atr, effective_max = portfolio_total_cap ←
                                                         ↓
            _with_climate_adjusted() → item["adjusted_status"] (保留原始 status 用于显示)
                                                         ↓
            build_roles(merged, max_total=effective_max)
              → allocate_weights(items, max_total=effective_max)
                → 用 adjusted_status 过滤 tradable
                → Score 占比分配 + ATR cap 约束 + 总量回退
                                                         ↓
            render_markdown(items, plan, market_level)
              → 用 adjusted_status 做判断，原始 status 用于显示
              → build_signal_summaries() → signal_state_for_item(..., market_level)
                                                         ↓
            输出: Markdown + JSON signals
```

---

## 6. 配置文件更新

### 6.1 `portfolio_run.py` 内置常量

`MARKET_DRAINAGE` 和 `portfolio_total_cap()` 在 `portfolio_run.py` 内直接定义，不需要额外 `config.py` 文件。原因：
- 降级逻辑只影响 portfolio skill 的仓位分配
- 其他 skill（trader、t0-trader）不受影响
- 避免引入新的文件/模块

### 6.2 `config.py` (portfolio skill) 仅需确认的常量

```python
# 已有的常量不需要改:
DEFAULT_MAX_TOTAL: int = 80
DEFAULT_CASH_FLOOR: int = 20
DEFAULT_MAIN_CAP: int = 50
LOOKBACK_DAYS: int = 60
```

---

## 7. 变更影响分析

| 文件 | 变更类型 | 影响 | 风险 |
|---|---|---|---|
| `final_portfolio.py` | `build_portfolio()` 调用 `portfolio_total_cap()` | 低 | 仅组合模式 |
| `portfolio_run.py` | 新增 `allocate_weights()`, `climate_adjust()`, `portfolio_total_cap()`, `_with_climate_adjusted()`；改造 `build_roles()` 和 `signal_state_for_item()` | 中 | 核心变化 |
| `test_portfolio_contract.py` | 新增 10+ 测试用例 | — | 需补充 |
| `trader_shared/` | 不改 | — | — |
| `candidate_core.py` | 不改 `target_weight()`（单票管线保留） | — | — |
| `market_env.py` | 不改 | — | — |

### 7.1 已知遗留问题（不在这次修）

`build_advice()` (`portfolio_run.py:637-658`) 生成 Markdown table（`| 标的 | 现价 |`），违反 AGENTS.md §7.2 的表格禁止规则。这是现有 bug，不在本次变更范围内，但应记录为 TODO。

---

## 8. 测试覆盖

新增/修改测试用例清单：

### 8.1 Score 分配测试

| 测试 | 验证 |
|---|---|
| `test_allocate_weights_two_stocks` | 2 只票，Score 85/60，验证权重比例 ≈ 85:60 |
| `test_allocate_weights_three_stocks` | 3 只票，Score 90/70/50 |
| `test_allocate_weights_atr_cap_hard_limit` | 高分票的 atr_cap 更低时，权重被 cap 住 |
| `test_allocate_weights_total_cap_override` | atr_cap 总和 > max_total 时，回退切割生效 |
| `test_allocate_weights_single_tradable` | 1 个 tradable，2 个暂不碰 |
| `test_allocate_weights_zero_scores` | 所有 score=0，均分 |
| `test_allocate_weights_negative_scores` | score 有负数，保底 30 |
| `test_allocate_weights_empty_tradable` | 全部暂不碰，返回 {} |
| `test_allocate_weights_no_ok_flag` | ok=False 的 item 不被分配 |

### 8.2 信号降级测试

| 测试 | 验证 |
|---|---|
| `test_climate_adjust_very_weak_downgrade` | 很差 + 低吸观察 → 防守观察 |
| `test_climate_adjust_normal_unchanged` | 正常 + 等转强 → 等转强 |
| `test_climate_adjust_empty_market` | 空 market_level → 不变 |

### 8.3 总仓上限联动测试

| 测试 | 验证 |
|---|---|
| `test_portfolio_total_cap_normal` | 正常/未知 → 80 |
| `test_portfolio_total_cap_weak` | 偏弱 → 70 |
| `test_portfolio_total_cap_weak_high_atr` | 偏弱+高波 → 60 |
| `test_portfolio_total_cap_very_weak` | 很差 → 60 |

### 8.4 集成测试

| 测试 | 验证 |
|---|---|
| `test_build_portfolio_with_market_filter` | 完整流程：大盘偏弱 → 信号降级 → 仓位下调 |
| `test_build_snapshot_portfolio_unchanged` | 快照模式不受影响 |
| `test_signal_state_with_climate` | signal_state_for_item 使用 adjusted_status |

---

## 9. 验证

```bash
# 单票分析不受影响
python3 scripts/final_report.py --target 南网科技

# 组合仓位 - 新增 Score 差异化分配
python3 scripts/final_portfolio.py --targets 南网科技 中国铝业

# Snapshot 模式不变
python3 scripts/final_portfolio.py --snapshot snapshot.json

# 自检
python3 scripts/self_check.py

# 运行测试（如有 pytest）
python3 -m pytest 01-功能包-packages/04-仓位轮动-trader-portfolio/tests/ -v
```

---

## 10. 不在本次范围内的内容

- 大盘判断逻辑本身（`market_env.assess()`）不改
- shared 模块（`candidate_core`, `signal_contract`）不改
- T0 盯盘信号冷却不改
- Pool 入池逻辑不改
- Snapshot 模式降级逻辑暂不实现（`choose_rotation()` 后续可扩展）
- `build_advice()` 表格语法 bug（现有，TODO 记录）
- `target_weight()` 删除（保留供其他 skill 使用）
