# Trader3.0 项目长期记忆

## 代码位置与提交约定

- **规范源码**：`02-共享模块-shared/trader_shared/` + `01-功能包-packages/trader/scripts/run_analysis.py`
- **⚠️ skill 双安装位**：`~/.workbuddy/skills/trader/`（本会话）+ `~/.hermes/skills/trader/`（pack_all 目标）。修复两边都打。digest 一致 `02c554c66579b09d`。
- **回灌仓库**：纯新增→整文件复制；已分叉→精合保留 repo 更新。禁止整文件覆盖分叉文件。
- 验证：仓库上下文实跑 `final_report.py` + `test_fusion_integration.py` 防回归。
- 提交落 Trader3.0 仓库，**默认不 push**。

## ⚠️ 数据源问题（2026-07-15 发现）

- **tushare HTTP 模式卡死**：SDK 缺失时降级到 HTTP（`fastapic.stockai888.top`），但该 API 不可达→进程 hang 死（SIGKILL/timeout）。`get_provider()` 优先选 tushare（token 存在+HTTP 可用→`available=True`），`TRADER_DATA_PROVIDER=tencent` 环境变量被跳过。
- **临时绕过**：在 Python 中 `from trader_shared.data_provider import UnifiedProvider, set_provider; set_provider(UnifiedProvider(backend="tencent"))` 强制切 tencent。
- **✅ 已修（2026-07-16，commit 93ff9c0）**：`tushare_client.py` 加 `_probe_reachable()`（独立线程 socket.connect + join 硬超时），`TushareClient.__init__` 初始化前先探测 `api_url`，不可达则整条通道标不可用→`get_provider()` 干净回退腾讯。沙箱可达时行为不变，Mac 不可达不再挂死。

## 决策框架（勿破坏）

- 融合层三评委：chan / momentum / vpf + HMM regime 动态权重。短线第三评委是 vpf，非 wyckoff。新增指标不当第 4 评委。
- 展示型指标走 `plugins/` + `display_only=True`，不污染 `weighted_score`。
- 止损：structure_core ATR trailing + stage_positioning 取高（只紧不松）。
- **combo / 箱体已暂停接入报告**（2026-07-14）：渲染接线已摘除，模块+单测保留。等价性基线 42 行无 combo 段，门禁 87 passed。

## 测试

- venv：`/Users/like/.workbuddy/binaries/python/envs/default/bin/python -m pytest`
- `PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts`（shared 在前）
- `test_contract.py` 有 3 项既有失败，非改动引入。
- CI 门禁：`scripts/run-gate-tests.sh` 锁 7 个离线测试（68 passed/~63s），`git config core.hooksPath scripts/git-hooks` 启用。
- **mock_seam 全链路 patch**：`get_env_for_skill` 经 re-export 到包命名空间，须同时打 3 处（源 market_env + 包级 trader_shared + 消费者 report_builder/report_presentation）。

## 模块命名冲突陷阱

- `trader_shared/report_renderer/` 是已追踪包（另一套渲染实验）。**切勿新建同名 `report_renderer.py`**。展示层已命名为 `report_presentation.py`。

## 大文件拆分方法论

- 用 AST 精确提取（`ast.get_source_segment`），不用 sed/行号切片。
- 等价性闸门：分裂前后跑全离线 mock 桩，日期掩码后 diff/md5，证明零回归。
- 测试桩全局改写必须走 `monkeypatch.setattr`。

## 已知技术债（2026-07-14 审计，大部分已修 commit aba3d51）

### 已修复（aba3d51 + 2026-07-16 复核确认）
- 威科夫 phase 持久化只进不退 → 改为基于 `_PHASE_ORDER` 符号判断反向翻转
- 中线威科夫回退日线 → 删回退分支，周线不足直接 insufficient
- 打分函数隐藏写盘 → 传 `use_persisted_phase=False`
- SOS 魔法数强耦合 → 改用 `[-1]`/`len()`/`WYCKOFF_DIVERGENCE_BARS-1`
- 缠论 D4：一类买卖「离开段」约束失效 → 新增 `_zone_last_end_index` 兼容 members/strokes
- 🔴 缠论行矛盾：`report_core.py:362-364` 已有 `_insufficient_struct` 守卫（wave_label_mid 含"笔数不足/无法判断/无明确结构/数据不足"时 `_chan_dir_mid` 强制为空、仅补"中性"），不再强叠方向词。2026-07-16 读码复核确认已修。
- 🟠 盘中合成 bar：`report_builder.py:146-148` 注释明确"合成 bar volume=0 绝不追加进 bars"，`live_bar` 仅用于价格/涨跌幅展示。2026-07-16 读码复核确认已修。

### 待修
- 🟡 动量不足返回 score=50/neutral 占位语义双关：`momentum_core.py:207` 默认 `score=50`、`:257` `direction="neutral"`；`fusion_core.py:646` 动量不足时亦用 `mom_score=50` 兜底。"真中性市"与"数据不足"在 score/direction 上无法区分，会污染融合层权重判定。
