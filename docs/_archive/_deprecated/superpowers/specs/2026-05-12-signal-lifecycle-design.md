# 信号生命周期设计

**日期**: 2026-05-12
**状态**: 设计阶段
**优先级**: 第 2 步（issues-and-fix-plan.md）

---

## 问题

当前信号系统有 3 套文件（signals.jsonl / signal_log.jsonl / signal_results.jsonl），但没有统一的生命周期模型。Signal ID 统一后（第 1 步），下一步是定义信号从生成到完成/过期的完整状态迁移。

核心问题：
- 信号没有显式状态，只能通过 `signal_type` 和文件存在性推断
- `check_recent()` 无法区分"还没算结果"和"结果不会再产生"
- 过期信号（如 T0 盯盘超时）没有标记方式

---

## 方案

轻量状态标注：给 signals.jsonl 每条记录加 `status` 字段，定义 3 种状态值和迁移规则。

### 状态定义

```
active      = 正在追踪，check_recent 会处理它
completed   = 结果已计算或已手动填写，check_recent 跳过
expired     = 信号已超期（如 T0 盯盘过期），不再追踪
(无 status) = 默认行为同 active
```

### 状态迁移

```
无 status (隐式 active)
  │
  ├─→ active (显式设置，保留追踪)
  │
  ├─→ completed
  │    原因: check_recent 计算结果 → signal_results.jsonl
  │          fill() 手动填写 outcome
  │
  └─→ expired
       原因: T0 盯盘超时未触发
             信号超过 N 天未处理（未来自动过期）
```

### 状态无效迁移

```
completed → any    ❌ 禁止。计算结果不可撤回
expired   → any    ❌ 禁止。过期不可恢复
```

**代码强制**：`set_signal_status()` 检查当前状态，拒绝非法迁移。

---

## 设置者

| 设置者 | 设置时机 | 设为什么 |
|--------|---------|---------|
| 创建时 | 不设 status（隐式 active） | (无字段) |
| `check_recent()` | 计算结果写入 signal_results.jsonl 后 | `completed` |
| `backfill()` | 同上 | `completed` |
| `monitor.py` (T0) | 盯盘信号超时未触发 | `expired` |
| `fill()` (手动) | 用户手动填写 outcome 后 | `completed` |

---

## 值校验

所有状态值必须在 `SIGNAL_STATUS_VALUES = {"active", "completed", "expired"}` 中。非法值写入时拒绝。

---

## check_recent 行为变化

`check_recent()` 和 `backfill()` 的信号遍历循环最前面新增状态检查：

```
for each signal:
    if status == completed or expired → skip (不计入 skipped 计数)
    if status == active or no status → 正常处理
```

---

## 持久化

signals.jsonl 记录新增 2 个可选字段：

```python
{
    "signal_id": "...",              # 统一 ID
    "signal_type": "low_buy_watch",  # 信号类型
    "status": "completed",           # 新增: 生命周期状态
    "status_updated_at": "2026-05-12T10:30:00",  # 新增: 状态更新时间
    # ... 现有字段
}
```

---

## 参考代码

### signal_tracker.py 新增

```python
# ── 信号生命周期状态 ──

SIGNAL_STATUS_VALUES = {"active", "completed", "expired"}

_FORBIDDEN_TRANSITIONS = {
    ("completed", "active"): True,
    ("completed", "expired"): True,
    ("expired", "active"): True,
    ("expired", "completed"): True,
}


def signal_is_trackable(sig: dict) -> bool:
    """信号是否应被 check_recent 处理。
    
    没有 status 字段 = active（默认追踪）
    status 为 active = 追踪
    status 为 completed/expired = 跳过
    """
    status = sig.get("status")
    if status is None:
        return True  # 默认 active
    return status == "active"


def set_signal_status(rec: dict, new_status: str) -> None:
    """设置信号状态，校验合法值和迁移规则。"""
    if new_status not in SIGNAL_STATUS_VALUES:
        raise ValueError(f"Invalid signal status: {new_status}")
    
    current = rec.get("status")
    if current and (current, new_status) in _FORBIDDEN_TRANSITIONS:
        raise ValueError(
            f"Transition not allowed: {current} → {new_status}"
        )
    
    rec["status"] = new_status
    rec["status_updated_at"] = datetime.now().isoformat()
```

### check_recent/backfill 改造

```python
for sig in recent:
    if not signal_is_trackable(sig):
        lifecycle_skipped += 1; continue
    # ... 现有计算逻辑

# 计算结果后设置 status = completed
if result:
    set_signal_status(result, "completed")
```

---

## 现有数据回填

部署后需运行一次迁移：对 signals.jsonl 中已有对应 signal_results.jsonl 记录的信号，设置 `status: completed`。

```python
def backfill_signal_status():
    """为现有信号补充 status 字段。
    
    已有结果记录的信号 → completed
    其余 → 不设 status（隐式 active）
    """
    results = set()
    for line in RESULT_PATH.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            results.add(r.get("signal_id"))
    
    lines = []
    for line in STORE_PATH.read_text().splitlines():
        if not line.strip():
            lines.append(line); continue
        sig = json.loads(line)
        if sig.get("status"):
            lines.append(line); continue  # 已有 status 的不改动
        if sig.get("signal_id") in results:
            sig["status"] = "completed"
            sig["status_updated_at"] = datetime.now().isoformat()
        lines.append(json.dumps(sig, ensure_ascii=False))
    
    STORE_PATH.write_text("\n".join(lines) + "\n")
```

---

## 不涉及

以下不在本次生命周期设计中：

- `signal_log.jsonl` 的状态迁移（该文件有独立的 `outcome` 字段，通过 `fill()` / `fill_by_target()` 管理）
- `signal_results.jsonl` 的状态（结果记录一旦写入就是终态）
- 超出初始 scope 的复杂状态机

---

## 依赖关系

- **前置**: Signal ID 统一模型（第 1 步）✅ 已完成
- **后置**: check_recent/backfill 修改后，所有旧信号（无 status）被视同 active，行为不变
- **schema 分层讨论**（第 3 步）：未来可在此生命周期基础上扩展
