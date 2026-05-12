# Signal ID 统一模型 (A-3)

**日期**: 2026-05-12  
**状态**: 设计阶段  
**优先级**: P1 — 最高优先级架构问题  

---

## 问题陈述

三套 JSONL 文件使用两套独立的主键体系，零交叉引用：

| 文件 | 当前 ID 模型 | 输入字段 | 哈希算法 |
|------|------------|---------|---------|
| `signal_log.jsonl` | `stable_id(skill, target(中文), date, type(中文), price)` | skill + 中文名 + 中文类型 | MD5[:12] |
| `signals.jsonl` ↔ `signal_results.jsonl` | `_make_signal_key(symbol, date, type(英文化), price) → 4-key 元组匹配` | 符号 + 英文类型 | SHA256 不生成 ID |

核心矛盾：signal_log 用 skill + 中文名，signal_results 用代码 + 英文名。两套 ID 永远无法关联，导致：
- `fills()` 找不到对应的结果
- `show` 无法跨表统计
- 无法建立信号生命周期追溯

---

## 统一方案

### signal_id 计算规则

```python
def make_signal_id(symbol, date, signal_type, price):
    """生成统一信号 ID — 唯一函数，所有写入侧共用。"""
    key = f"{symbol}|{date}|{signal_type}|{price}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

**输入字段规范化**（统一在调用方处理）：

| 字段 | 规范化规则 | 默认值 | 示例 |
|------|-----------|--------|------|
| `symbol` | `_normalize_symbol()` | 空字符串 | `688248.SH` |
| `date` | `_norm_date()` | 空字符串 | `2025-05-02` |
| `signal_type` | `_normalize_signal_type()` | `"unknown"` | `low_buy_watch` |
| `price` | `_price_from_trigger()` 或 `"0.00"` | `"0.00"` | `10.50` |

### 双字段共存策略（signal_log.jsonl）

signal_log.jsonl 同时保留新旧 ID：

```python
record = {
    "signal_id_md5": old_md5,  # 旧 ID，保留用于 fill() 兼容
    "signal_id": sig_id_v2,    # 新统一 ID
    "signal_type": signal_type, "price": price,
    # ... 其余字段不变
}
```

旧记录只有 `signal_id`（MD5）和 `signal_id_md5` 字段为空。`fill()`` 和 dedup 逻辑同时检查两个字段。

### 为什么不含 `skill`

| 方案 | 结果 |
|------|------|
| 含 skill | signal_log 和 signal_results 永远不匹配 → 统一 ID 目标失败 |
| 不含 skill | 同票同日同类型信号去重（表达同一件事，合并更合理） |

`source_skill` 字段在每条记录中保留，用于追溯来源。

### 熵分析

SHA256[:16] = 48 bits → 生日边界约 2^24 ≈ 1600 万条记录。当前系统每日约 10-30 条信号，48 位足够。

---

## 改造点

### 1. 新增 `make_signal_id()`

```python
def make_signal_id(symbol: str, date: str, signal_type: str, price: str) -> str:
    """生成统一信号 ID。"""
    key = f"{symbol}|{date}|{signal_type}|{price}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

### 2. `signal_store.append_signal()` 兜底

```python
def append_signal(signal: dict, path=None):
    assert_valid_signal(signal)
    if "signal_id" not in signal:
        raw_type = str(signal.get("signal_type") or "unknown").strip()
        sig_id = make_signal_id(
            symbol=_normalize_symbol(str(signal.get("symbol") or "")),
            date=_norm_date(str(signal.get("trade_date") or "")),
            signal_type=_normalize_signal_type(raw_type),
            price=_price_from_trigger(signal) or "0.00",
        )
        signal["signal_id"] = sig_id
    # ... 写入逻辑不变
```

### 3. `signal_log.jsonl` 写入侧

```python
def log_safe(skill, target, symbol, signal_type, price, env_level="", env_note=""):
    today = _today()
    norm_type = _normalize_signal_type(str(signal_type))
    sig_id_v2 = make_signal_id(
        symbol=_normalize_symbol(symbol or ""),
        date=today,
        signal_type=norm_type,
        price=f"{float(price):.2f}" if price else "0.00",
    )
    old_md5 = hashlib.md5(f"{today}::{skill}::{target}::{signal_type}".encode()).hexdigest()[:12]
    # 双字段共存写入
```

Dedup 改为查 `signal_id`（优先）+ `signal_id_md5`（降级）：
```python
if not LOG_PATH.exists():
    _create_log_record(sig_id_v2, old_md5, ...)
    return sig_id_v2
for line in LOG_PATH.read_text().splitlines():
    try:
        rec = json.loads(line)
        if rec.get("signal_id") == sig_id_v2 or rec.get("signal_id_md5") == old_md5:
            return sig_id_v2
    except: continue
_create_log_record(sig_id_v2, old_md5, ...)
```

### 4. `signal_results.jsonl` 写入侧

`_compute_results_for_sig()` 返回结果时写入 `signal_id`：

```python
res = {
    "signal_id": make_signal_id(norm_symbol, norm_date, norm_type, price_str),
    # ... 其余字段不变
}
```

### 5. 读写匹配三级降级

`check_recent()` / `backfill()` 匹配逻辑升级：

```
1. signal_id 精确匹配 → 跳过
2. 4-key 匹配（对 read-back 的 signal_date 调用 _norm_date，对 signal_type 调用 _normalize_signal_type） → 跳过
3. 3-key 匹配（同上规范化） → 跳过
4. 计算新结果
```

**关键修正**：现有代码中 4-key 和 3-key 都使用原始 `signal_date` 字符串（未调用 `_norm_date`）。升级后：

```python
for line in RESULT_PATH.read_text(encoding="utf-8").splitlines():
    if not line.strip(): continue
    try:
        r = json.loads(line)
        raw_date = str(r.get("signal_date", ""))
        raw_type = str(r.get("signal_type", ""))
        norm_date = _norm_date(raw_date)
        norm_type = _normalize_signal_type(raw_type)
        sp = r.get("signal_price")
        price_str = f"{float(sp):.2f}" if sp is not None and float(sp) > 0 else ""
        existing_keys_4[(_normalize_symbol(r.get("symbol", "")), norm_date, norm_type, price_str)] = r
        existing_keys_3[(_normalize_symbol(r.get("symbol", "")), norm_date, norm_type)] = r
    except (json.JSONDecodeError, ValueError):
        pass
```

**信号匹配字段映射表**（结果记录 → 输入信号字段）：

| make_signal_id 输入 | 来源（signal.jsonl） | 来源（signal_results.jsonl） |
|---|---|---|
| symbol | `signal["symbol"]` → `_normalize_symbol` | `result["symbol"]` → `_normalize_symbol` |
| date | `signal["trade_date"]` → `_norm_date` | `result["signal_date"]` → `_norm_date` |
| signal_type | `signal["signal_type"]` → `_normalize_signal_type` | `result["signal_type"]` → `_normalize_signal_type` |
| price | `_price_from_trigger(signal)` or `"0.00"` | `f"{float(result['signal_price']):.2f}"` |

**read-side backward compatibility**（读取侧向后兼容）：

每个匹配函数必须使用相同的规范化路径。以下函数需要检查改造：
- `check_recent()` — existing_keys 构建（见上文）
- `backfill()` — same as check_recent
- `show_single()` — 不影响（按 symbol/name 显示）
- `load_recent()` — 不影响（按 skill/target/symbol/filter）

---

## 架构假设

- **单进程写入**：当前系统无并发写入。JSONL append 不保证原子性（现有代码已用 tmp+os.replace 缓解）。不引入分布式锁或多进程同步。
- **文件大小**：假设单文件 < 10MB（内存读取可接受）。超过此阈值需引入索引文件。
- **幂等写入**：`append_signal()`、`log_safe()`、`check_recent()` 都有 dedup，重复调用不会产生重复记录。

---

## 特殊场景

### review_result 同天多票

同一票同一天的 review_result 信号可能有多条（缠论/威科夫/筹码分别触发）。price 统一为 "0.00"，signal_type 均为 "review_result"。

**修正 1 — 始终保留 4 字段 arity**：不在 key 中追加 extra_hash，而是将 trigger_text hash 作为**独立可选字段**写入记录，不在 make_signal_id key 中改变字段数量：

```python
def make_signal_id(symbol, date, signal_type, price):
    """始终 4 字段，不改变 arity。"""
    key = f"{symbol}|{date}|{signal_type}|{price}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

review_result 记录额外写入一个 `signal_id_tag` 字段供 dedup 使用：

```python
# review_result 写入时
sig_id = make_signal_id(norm_symbol, norm_date, "review_result", "0.00")
record = {"signal_id": sig_id, ...}
if trigger_text:
    record["signal_id_tag"] = hashlib.sha256(trigger_text[:40].encode()).hexdigest()[:8]
```

**修正 2 — dedup 时检查**：`log_safe()` 对 review_result 类型使用 signal_id_tag 做二次区分：

`log_safe()` 的 dedup 逻辑改为：

```python
# review_result 类型的 dedup（两条同票同天但不同 trigger_text 的记录）：
# 若 symbol + date + type + price 全匹配（即 signal_id 相同）：
#   - 若两条都有 signal_id_tag 且不同 → 不 dedup（视为两条不同 review）
#   - 否则 → 正常 dedup
# 其他类型 → 正常 signal_id 匹配 dedup
```

> `review_result` 不参与结果匹配（outcome 为空），ID 区分度只在写入侧需要。read-side 无需特殊处理。

---

## 向后兼容

### fill() 旧 MD5 ID 降级

用户调用 `fill("abc123def456")`（旧 MD5 12 位）：

```python
def fill(signal_id, pnl_pct, days_held=0, outcome="unknown"):
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    new_lines = []
    updated = False
    for line in lines:
        if not line.strip():
            new_lines.append(line)
            continue
        try:
            rec = json.loads(line)
        except:
            new_lines.append(line)
            continue
        
        # 匹配新 ID 或旧 MD5 ID
        matched = (rec.get("signal_id") == signal_id or 
                   rec.get("signal_id_md5") == signal_id)
        
        if matched and rec.get("outcome_pnl_pct") is None:
            rec["outcome_pnl_pct"] = round(pnl_pct, 2)
            rec["outcome_days"] = days_held
            rec["outcome"] = outcome
            rec["filled_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            updated = True
            # 若信号_id_md5 等于传入的 signal_id → 确认是旧记录
            if rec.get("signal_id_md5") == signal_id:
                rec["signal_id"] = make_signal_id(
                    symbol=_normalize_symbol(rec.get("symbol") or ""),
                    date=_norm_date(str(rec.get("timestamp", "") or "")[:10]),
                    signal_type=_normalize_signal_type(rec.get("signal_type") or "unknown"),
                    price=f"{float(rec.get('price') or 0):.2f}",
                )
        
        new_lines.append(json.dumps(rec, ensure_ascii=False))
    
    if updated:
        tmp = LOG_PATH.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        fd = os.open(str(tmp), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp), str(LOG_PATH))
        return True, "ok"
    return False, "signal_id not found"
```

**关键不变量**：`fill()` 命中旧记录时，通过检测 `signal_id_md5 == signal_id` 确认，自动补充 `signal_id` 字段，维护 `"已更新记录必含新 ID"` 不变量。

### 旧记录不动

已存在的旧 JSONL 记录不主动修改。新增两条记录：
- `signal_log.jsonl`：旧记录不添加 `signal_id_v2`（只对新记录添加）；`fill()` 命中旧记录时会补充
- `signal_results.jsonl`：旧记录补充 `signal_id` 通过 `migrate_signal_ids()` 完成

---

## 迁移策略

### Phase 1: 写入新增 signal_id

- `make_signal_id()` 上线
- `append_signal()` 兜底补充 signal_id
- `log_safe()` 写入新 signal_id（双字段共存）
- `_compute_results_for_sig()` 写入 signal_id
- 旧代码全部保留

### Phase 2: 迁移工具

`migrate_signal_ids()` 为旧 `signals.jsonl` 和 `signal_results.jsonl` 记录补充 `signal_id`。

**幂等策略**：已带 `signal_id` 的记录跳过。**绝不覆盖已有 `signal_id`**（防止部分运行的记录产生不一致）。

**signals.jsonl 处理**（每个记录）：
1. 跳过已带 `signal_id` 的记录
2. 提取 `symbol` → `_normalize_symbol()`
3. 提取 `trade_date` → `_norm_date()`
4. 提取 `signal_type` → `_normalize_signal_type()`
5. 提取 price → `_price_from_trigger() or "0.00"`
6. 计算 `signal_id` → 写入
7. 原子 write（tmp + os.replace）

**signal_results.jsonl 处理**（每个记录）：
1. 跳过已带 `signal_id` 的记录
2. 提取 `symbol` → `_normalize_symbol()`
3. 提取 `signal_date` → `_norm_date()`
4. 提取 `signal_type` → `_normalize_signal_type()`
5. 提取 price → `f"{float(result['signal_price']):.2f}"`
6. 计算 `signal_id` → 写入
7. 原子 write（tmp + os.replace）

**异常处理**：
- 坏行（JSONDecodeError）：跳过，不写入，不丢失其他记录
- 字段缺失：使用默认值（symbol="" → 空字符串 hash）
- 中途终端：已写入的记录不丢失（tmp + os.replace 保证），下次运行重新执行幂等

```python
def migrate_signal_ids(path=None):
    """为旧 signals.jsonl 和 signal_results.jsonl 记录补充 signal_id。
    
    幂等：已带 signal_id 的记录跳过。
    不处理 signal_log.jsonl — 旧 MD5 ID 不可逆（已存保留，fill() 自动补充）。
    """
    # 1. signals.jsonl — 逐行处理
    store_path = path or DEFAULT_SIGNAL_STORE_PATH
    _migrate_file(store_path, is_signal=True)
    
    # 2. signal_results.jsonl — 逐行处理
    result_path = Path.home() / ".trader" / "signal_results.jsonl"
    _migrate_file(result_path, is_signal=False)


def _build_signal_id_inputs(result_rec):
    """从信号或结果记录中提取 make_signal_id 所需字段。"""
    # signal 记录 (signals.jsonl): signal_type, trigger.price, symbol, trade_date
    # result 记录 (signal_results.jsonl): signal_type, signal_price, symbol, signal_date
    norm_symbol = _normalize_symbol(str(result_rec.get("symbol", ""))) or ""
    
    if result_rec.get("trigger", {}).get("price"):
        price_str = f"{float(result_rec['trigger']['price']):.2f}"
    elif result_rec.get("current"):
        price_str = f"{float(result_rec['current']):.2f}"
    elif result_rec.get("signal_price"):
        price_str = f"{float(result_rec['signal_price']):.2f}"
    else:
        price_str = "0.00"
    
    # date 字段可能叫 trade_date (signal) 或 signal_date (result)
    date_val = result_rec.get("trade_date") or result_rec.get("signal_date", "")
    norm_date = _norm_date(str(date_val)) or ""
    norm_type = _normalize_signal_type(str(result_rec.get("signal_type", "unknown")))
    
    return norm_symbol, norm_date, norm_type, price_str

def _migrate_file(file_path, is_signal=True):
    if not file_path.exists():
        return
    
    new_lines = []
    migrated = 0
    skipped = 0
    
    for line in file_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            new_lines.append(line)
            continue
        
        try:
            rec = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            new_lines.append(line)
            continue
        
        if rec.get("signal_id"):
            new_lines.append(line)
            skipped += 1
            continue
        
        norm = _build_signal_id_inputs(rec)
        rec["signal_id"] = make_signal_id(*norm)
        new_lines.append(json.dumps(rec, ensure_ascii=False))
        migrated += 1
    
    if migrated > 0:
        tmp_path = file_path.with_suffix(".jsonl.tmp")
        tmp_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        fd = os.open(str(tmp_path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp_path), str(file_path))
    
    return {"migrated": migrated, "skipped": skipped}
```

**调用方式**：
```bash
python -c "from signal_tracker import migrate_signal_ids; migrate_signal_ids()"
```
用户手动运行一次，后续不再需要。

### Phase 3: 清理旧 ID 函数

- `stable_id()` 标记 deprecated
- 移除从 `stable_id()` 的间接引用
- 不再需要独立的 `fill_old()` — `fill()` 已合并新旧 ID 降级逻辑

### Phase 4: 移除降级逻辑

- 移除 `fill()` 的旧 ID 降级
- 移除 4-key / 3-key 降级（signal_id 成唯一匹配标准）
- 完全清理 `stable_id()` 函数

---

## 测试计划

### 单元测试（新增）

1. `make_signal_id()` 基础 — 确定性、长度（16 字符）、SHA256 碰撞概率
2. 符号规范化 — `688248` / `688248.SH` / `688248.sh` → 同 ID
3. 日期规范化 — `2025-5-2` / `2025-05-02` / `2025-05-02T14:00:00` → 同 ID
4. 信号类型归一化 — `低吸观察` / `low_buy_watch` → 同 ID
5. price 缺失 — `"0.00"` 兜底，有 price 时使用实际值
6. **price 区分** — `make_signal_id("A", "2025-01-01", "low_buy_watch", "10.50")` ≠ `make_signal_id("A", "2025-01-01", "low_buy_watch", "10.51")`
7. review_result 特殊处理 — trigger_text[:40] hash 前缀区分、短文本 ≤20 字符、空文本
8. `_normalize_signal_type()` — 所有 30+ 映射 + 标准名透传

### 集成测试

1. **signals.jsonl → signal_results.jsonl 匹配** — check_recent 优先用 signal_id 匹配
2. **signal_log.jsonl dedup** — log_safe 双字段去重（signal_id + signal_id_md5）
3. **三级降级匹配** — 旧记录（无 signal_id）用 4-key / 3-key 正常匹配
4. **fill() 旧 ID 降级** — 传入旧 MD5 ID，通过单遍扫描 signal_id_md5 降级更新记录
5. **mixed-phase** — 旧记录 + 新记录共存时 dedup 正常工作
6. **3-key 降级** — `2025-4-1`（非归一化）与 `2025-04-01` 匹配

### 迁移测试

1. `migrate_signal_ids()` 幂等 — 运行两次不产生重复或侧效应
2. `migrate_signal_ids()` 坏行容错 — 文件含 JSONDecodeError 行，跳过并保留
3. `migrate_signal_ids()` 旧记录不丢失 — 所有非坏行都被处理

### 回归测试

- 现有 243 个 shared tests 全部通过
- signal_tracker test suite 全部通过

---

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 旧记录无 signal_id，降级匹配慢 | 大文件时全表扫描 | 保持 4-key + 3-key 索引作为第二级 |
| review_result 多条同票同天碰撞 | 后写入的被 dedup | review_result 加 trigger_text hash |
| fill() 旧用户调用失效 | 手动复盘无法更新 | 降级兼容：单遍扫描同时查 signal_id 和 signal_id_md5 |
| 迁移工具中断 | 部分旧记录无 ID | Phase 1 不删旧代码；migrate 原子写回 |
| signal_store.py vs signal_tracker.py `_normalize_symbol` 不一致 | 两边算出不同 ID | 函数提取到 `signal_utils.py`，共用单一实现 |
| 3-key 降级 `signal_date` 未规范化 | `2025-4-1` 与 `2025-04-01` 不匹配 | 3-key 构建时对 `signal_date` 调用 `_norm_date()` |
