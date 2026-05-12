# 选股池融合集成 Implementation Plan

**Goal:** Store fusion data in pool records, display in show/compare/rank.

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `03-选股池-trader-pool/scripts/final_pool.py` | Modify | record_from_report + show + rank + compare fusion integration |
| `03-选股池-trader-pool/tests/test_pool_contract.py` | Modify | Add fusion field tests |

### Task 1: Store fusion data in pool records

**Files:**
- Modify: `final_pool.py`

- [ ] **Step 1: Find `record_from_report`** and add fusion storage

```bash
grep -n "def record_from_report" 01-功能包-packages/03-选股池-trader-pool/scripts/final_pool.py
```

Add inside `record_from_report()`, where the record dict is built:

```python
    # 融合层数据
    fusion = report.get("fusion", {}) or {}
    record["fusion_action"] = fusion.get("action")
    record["fusion_confidence"] = fusion.get("confidence")
    record["fusion_score"] = fusion.get("weighted_score")
```

- [ ] **Step 2: Test — read back and verify**

Run pool commands after adding: `pool show 688248` should include fusion data.

- [ ] **Step 3: Commit**

```bash
git add 01-功能包-packages/03-选股池-trader-pool/scripts/final_pool.py
git commit -m "pool: store fusion data in pool records"
```

### Task 2: Show fusion in cmd_show

**Files:**
- Modify: `final_pool.py`

- [ ] **Step 1: Find cmd_show output section**

Find where show renders each item line. Add fusion inline:

```python
# On the item line, append fusion info if available:
item_line = f"  {name}({code})  | 场景:{scene}({score})  ATR:{atr_text}"
if item.get("fusion_confidence"):
    item_line += f"  | 融合:{item.get('fusion_action', '?')}({item['fusion_confidence']})"
```

### Task 3: Use fusion in cmd_rank sorting

**Files:**
- Modify: `final_pool.py`

- [ ] **Step 1: Find sort_items usage in rank**

```bash
grep -n "sort_items\|sort.*key" 01-功能包-packages/03-选股池-trader-pool/scripts/final_pool.py
```

Add fusion_confidence as secondary sort:

```python
items.sort(key=lambda i: (i.get("fusion_confidence") or 0, ...), reverse=True)
```

### Task 4: Show fusion in cmd_compare

- Show `融合: action(conf)` after each stock block.

### Task 5: Full regression

- [ ] Run pool tests
- [ ] Run shared tests
- [ ] Commit and merge
