# 六闸口契约（P1）

> **状态**：P1 冻结  
> **版本**：v0.1 · 2026-07-18  
> **实现**：`trader_shared/strategy_match.py`（P2）  
> **架构**：`strategy-layered-architecture.md`

---

## 1. 闸口链

```text
select → entry → manage → scale → take → stop
```

每闸 **最多 1 个 primary**；`candidates` 最多展示 1 个。

---

## 2. 各闸 IO

### 2.1 `select` 选股/入池

| | |
|--|--|
| **只回答** | 能否进池/留池/是否观察否决 |
| **输入** | `regime`, `wyckoff.event_code`, `chip.support_tag`, `chip.trapped_tag`, `action_block_new` |
| **输出** | `primary`, `mode=active`, `veto_entry: bool` |
| **包** | `select.observe_G`（兜底）, `select.defense_E`（否决） |
| **veto_entry** | defense_E 命中 → true，entry 不得 active |

### 2.2 `entry` 买/开仓

| | |
|--|--|
| **只回答** | 未持仓是否试探、价区与初始风险叙事 |
| **输入** | `has_position`, `allow_new_entry`, `checklist_all_green`, `chan.type_short`, select.veto |
| **输出** | `primary`, `mode=plan\|active\|off` |
| **包** | `entry.chan_buy1_probe` 等 |
| **规则** | has_position → off；veto 或 not allow_new_entry 或 not all_green → 最多 plan |

### 2.3 `manage` 持/管单

| | |
|--|--|
| **只回答** | 持仓后止损如何跟、阶段 S1/S2/S3 |
| **输入** | `has_position`, `cost`, `current`, `support`/`stop`（地板） |
| **输出** | `primary`, `mode`, `stage_id`, `stop_price`, `floor_price`, `stop_policy` |
| **包** | `manage.wyckoff_trail` |
| **规则** | 无持仓 → plan 预案；无 cost → 不得 S2 |

### 2.4 `scale` 加仓

| | |
|--|--|
| **只回答** | 允许/禁止加仓 + 上限提示 |
| **输入** | `has_position`, `checklist_all_green`, `allow_new_entry`, select.veto |
| **输出** | `mode=allow\|deny`, `reason` |
| **P2** | 最小实现：无持仓 deny；有持仓且 all_green 且非 veto → allow 文案，否则 deny |

### 2.5 `take` 止盈

| | |
|--|--|
| **只回答** | 是否建议分批摘果 |
| **输入** | `has_position`, `cost`, `current`, 浮盈 |
| **输出** | `mode=plan\|off`, `hint` |
| **P2** | 有持仓且浮盈≥阈值 → plan 提示分仓；否则 off（完整 F 包 P4） |

### 2.6 `stop` 止损

| | |
|--|--|
| **只回答** | 证伪是否跑、价、是否全清 |
| **输入** | manage 的 floor/stop_price 或 report `stop` |
| **输出** | `stop_price`, `stop_policy=全清`, `triggered`（价≤止损时 true） |
| **纪律** | **触发=一次性全清**，不分批死扛 |

---

## 3. 互斥（强制）

| ID | 规则 |
|----|------|
| M1 | stop.triggered → scale=deny，take 不鼓励加仓叙事 |
| M2 | select.veto_entry → entry.mode 不得 active |
| M3 | has_position → entry.mode=off（或只读） |
| M4 | not has_position → manage/take 不得伪装已持仓执行（mode=plan） |
| M5 | 同闸仅 1 primary（priority 最大） |

---

## 4. 包命名

```text
{gate}.{name}
```

例：`select.observe_G`, `entry.chan_buy1_probe`, `manage.wyckoff_trail`, `stop.invalidate_full`

---

## 5. mode 语义

| mode | 含义 |
|------|------|
| `active` | 当前应按此执行（文案可「止损挂 xx」） |
| `plan` | 预案/若开仓则… |
| `off` | 本闸不适用 |
| `allow` / `deny` | 仅 scale |
| `hard` | stop 闸展示纪律 |

---

## 6. 验收 G-01～G-04

见 `tests/test_strategy_match.py` 文档断言 + 匹配用例；本文件即 G-01/G-02 正文，G-03/G-04 由 S-01/S-02/S-04 覆盖。
