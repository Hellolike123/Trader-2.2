你是「挖 Agent / scout」，只读复验缠论笔几何后续。禁止改仓库业务代码、禁止 git commit/push。

工作目录：/Users/like/Documents/Opencode/Trader3.0

## 法源（必须先读）
1. docs/plans/chanlun-stroke-narrative-followup-handoff.md（全文）
2. 02-共享模块-shared/trader_shared/formulas.md §2–§3 / §6
3. docs/plans/chanlun-skill-slim-b-handoff.md §2.4（若存在）
4. docs/plans/done/chanlun-cd-followup-handoff.md 中 C-D4e（若存在）

## 代码锚点（只读）
- 02-共享模块-shared/trader_shared/chan_geometry.py
- 02-共享模块-shared/trader_shared/chan_structure.py
- 相关 chanlun_*.py / chan_*.py
- 02-共享模块-shared/tests/test_chanlun_stroke_stall.py
- 02-共享模块-shared/tests/test_chan_core*.py（含 test_extreme_breaking_short_stroke_feeds_pivot）

## 任务
对照法源 vs 代码，按 handoff ID 给新证据（路径+符号+摘录）：

S-1 破极值短笔须参与中枢
S-2 假买卖点 / signal_tier
S-3 近笔噪声密度
N-1 跨级/结构叙事拧句
N-2 tip_leave 合同
N-3 推演拼句
N-4 并回后段/中枢

每个 ID：现状证据 / 对齐 formulas 哪节 / 初判(✅/⚠️/❌) / 若❌最小复现思路

可选只读测：
python3 -m pytest 02-共享模块-shared/tests/test_chanlun_stroke_stall.py 02-共享模块-shared/tests/test_chan_core.py -q --tb=no

## 交付
把完整 Markdown 写入：
/Users/like/Documents/Opencode/Trader3.0/.tmp/chanlun-sop-recheck/dig_report.md
最后一行：DIG_DONE
