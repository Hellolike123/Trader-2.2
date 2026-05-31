## 1. 严重修复

- [x] 1.1 `decision_core.py:316-322` — 将 `_fake_break` 的 `prev_close >= support` 改为 `prev_close >= hard_stop`

## 2. 中等修复

- [x] 2.1 `main_force.py:158` — 阶段平局增加显式优先级：`markup > accumulation > testing > distribution > markdown`
- [x] 2.2 `fusion_core.py:180-200` — `_score_to_confidence` 在 score<50 时将分母从 10 改为 9，修复 40/41 不连续
- [x] 2.3 `fusion_core.py:266-272` — `_apply_main_force_weights` 在 clamp 后重新计算 total 并归一化
- [x] 2.4 `chip_distribution.py:118` — `decay_rate` 增加最低值 `max(decay_rate, 0.01)`
- [x] 2.5 `stage_positioning.py:302-315` — 置信度门限从 60 降到 50
- [x] 2.6 `stage_positioning.py:539-542` — 删除 `elif is_locked` 死代码，改为在 `if is_locked` 内部区分新锁定和已锁定
- [x] 2.7 `stage_positioning.py:642` — 派发阶段止损从 `MA20 * 1.02` 改为 `MA20 * 0.98`
- [x] 2.8 `decision_core.py:473-485` — 未知状态返回 `STATUS_SCORE.get("等转强", 60)` 而非 0
- [x] 2.9 `decision_core.py:525-532` — ATR 止损缓冲随波动率调整：高波动用 2.5×，低波动用 1.5×
- [x] 2.10 `structure_core.py` — `confirm_buffer` 增加 clamp `max(0.5, min(2.0, confirm_buffer))`
- [x] 2.11 `structure_core.py:279` — HMM 混合改为 `base * 0.5 + hmm_target * 0.5`，hmm_target 为 HMM 推荐中性值
- [x] 2.12 `signal_utils.py:159-160` — 带 `.` 的 symbol 增加后缀校验（按代码段判断正确后缀）

## 3. 低优先级修复

- [x] 3.1 `main_force.py:201` — `_calc_price_change` 数据不足返回 None，调用方检查 None
- [x] 3.2 `fund_flow_data.py:139-154` — 连续流入/流出在 net_flow=0 时视为当前方向延续
- [x] 3.3 `fund_flow_data.py:133-136` — `cum_5` 不足 5 天时返回 0 并标注实际天数

## 4. 验证

- [x] 4.1 跑全量测试确认无回归：`python3 -m pytest 02-共享模块-shared/tests/ -q`（593 passed）
- [x] 4.2 为假跌破修正添加测试：验证跌破止损位但无近期高于止损的收盘→真跌破
