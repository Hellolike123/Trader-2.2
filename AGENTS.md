## 接手先看

- **目标架构法源**：`docs/designs/resonance-and-orchestration.md` — 五层+编排、岗位共振；fusion 不作总司令。
- **版本**：Trader 2.4+（三技能：`trader` / `t0` / `review`）。单票**始终**中短线双轨（`render_short_midline`；`SHORT_MIDLINE_REPORT=false` 已忽略）。
- **Fusion 生产路径**：`FUSION_FROM_CARDS` 缺省 = `cards`；`classic` / `compare` 仅对照（classic deprecated）。详见 `BUSINESS.md` §2.7。
- **门禁**：`scripts/run-gate-tests.sh`（离线子集）；禁止把全量历史红项塞进门禁。说明：`docs/architecture/ci-gate.md`。
- **Agent 快路径**：各 skill **只预读** `references/agent-quickstart.md` + 共用 `references/agent-rules.md`；跑脚本 → 原样贴 markdown → 停。禁止开工前批量读 references、禁止默认 `--output json`。
- **命令 cwd**：Skill 包内用 `python3 scripts/...`；仓库根用 `python3 01-功能包-packages/<skill>/scripts/...`。仓位轮动在 **review** 包（无独立 `portfolio/` 包）。
- **中短线双轨**：`report_core.render_short_midline`；中线关键价用 `mid_key_prices`（周线），禁止日线 `key_levels` 冒充。
- **纪律只收紧**：`mistery_gate` + `chan_discipline` → `merge_discipline`；不改 major_stage / fusion 分 / support / stop。开仓清单 C1 见 `chan_discipline.format_entry_line_c1`。
- **方向**：以 `fusion.weighted_score` / decision_view 为准，不得从阶段/动能直接推断方向。
- **T0 v2**：人读结构仪表盘（`docs/t0-strategy-v2.md`），禁止「可执行/可低吸/三重共振买」指令叙事。
- **输出契约**：`01-功能包-packages/trader/references/output-template.md` 与 `render_short_midline` 同源。实现锚点：`report_core` / `report_builder` / `report_pipeline`。
- **深度与满分示例**：性能史、算法细节、微信端满分范例 → [`AGENTS_DEEP.md`](AGENTS_DEEP.md)。

改报告格式：`short_midline.py` → 刷新 golden →（骨架变了再）`output-template.md`。完整防漏清单：`01-功能包-packages/_common/agent-rules.md`。

---

## 改代码去哪（编程 Agent）

路径均相对 `02-共享模块-shared/trader_shared/`，除非另写包路径。

| 要改什么 | 改哪里（真相） | 勿改 |
|----------|----------------|------|
| 单票编排顺序 | `report_builder.py` | 在 stage 里堆无关业务 |
| 流水线阶段 | `report_pipeline/{fusion,structure,chip,assemble,context}_stage.py` 等 | 把大段逻辑塞回 builder |
| 短中线挂接 | `report_pipeline/attach_*.py`（facade=`attach.py`） | 把胶水写回 monolith `attach.py` |
| 短中线文案 | `report_renderer/short_midline.py` | 手拼面板 / 改旧 `📍 决策` |
| 行情类型 SSOT | `market_types.py`（`Security`/`MarketSnapshot`） | 在 light_data/data_provider 再各造一份 |
| Fusion 生产路径 | `fusion_core.py` + `analysis/cards.py` + `fusion_card_signals.py` | 加厚 classic 当主路径 |
| Classic 映射（对照） | `fusion_classic_mappers.py`（动量已委托 cards） | 在 cards 路径复制一份映射 |
| T0 盯盘缓存 | `t0_monitor._cached_build_plan`（`T0_PLAN_TTL_SEC`） | 每 tick 无脑全量 `build_plan` |
| 选股池逻辑 | `01-功能包-packages/trader/scripts/pool_cmds/*` | 把逻辑写回 `final_pool.py` |
| T0 引擎 | `t0_core.py` / `t0_run.py` / `t0_monitor.py` / `t0_*.py` | 只改包内 shim 正文 |
| 复盘 / 仓位 | `review_core.py` / `review_render.py` / `portfolio_*.py` | 在 skill 包复制实现 |
| Skill 包内 `scripts/*.py` | identity shim（`sys.modules[__name__] = _impl`） | 复制一份完整引擎 |

铁律：

1. **引擎只在 `trader_shared/`**；`01-功能包-packages/{t0,review}/scripts/` 下同名文件是 shim，靠模块身份替换保证 monkeypatch。
2. **`final_pool.py` 只做 CLI 薄入口**；入池/评分/plan/rank 进 `pool_cmds/`（如 `scoring.py`、`plan_view.py`）。
3. **改输出**：`short_midline.py` → 刷新 golden → 骨架变了再动 `output-template.md`。
4. **运行侧 Agent** 仍只读 `agent-quickstart.md`（跑脚本贴 markdown）；**改实现**以本表 + 法源为准。

---

## 业务全景

A 股交易决策辅助系统。免费行情 + 缠论 / 威科夫 / 筹码 / ATR，输出标准化 Markdown 面板。

主契约：**中短线双轨 + 纪律出手**。旧 `🎯`+`📍 决策` 不得再当主输出。  
接入 AI：先读本页摘要 → skill `agent-quickstart` → **跑脚本贴 markdown**，禁止凭记忆拼旧面板。

---

## Skill 速查表

| Skill | 一句话 | 入口（仓库根） |
|-------|--------|----------------|
| `trader` | 单票分析 + 选股池 | `01-功能包-packages/trader/scripts/final_report.py` / `final_pool.py` |
| `t0` | 盘中结构参考卡 + 盯盘 | `01-功能包-packages/t0/scripts/final_t0.py` |
| `review` | 盘后复盘 + 仓位轮动 + 信号追踪 | `01-功能包-packages/review/scripts/final_review.py` / `final_portfolio.py` / `final_tracker.py` |

运维（非 Skill）：`scripts/run_trader.py`、`scripts/t0_cron.py`、`scripts/wechat_monitor.py`。

---

## 推荐工作流

```
新票验票 → python 01-功能包-packages/trader/scripts/final_report.py --target <NAME>
入池 → python 01-功能包-packages/trader/scripts/final_pool.py add --target <NAME>
排序 → python 01-功能包-packages/trader/scripts/final_pool.py rank
明日作战表 → python 01-功能包-packages/trader/scripts/final_pool.py plan
盘中执行 → python 01-功能包-packages/t0/scripts/final_t0.py --target <NAME> --monitor
盘后复盘 → python 01-功能包-packages/review/scripts/final_review.py --target <NAME>
仓位轮动 → python 01-功能包-packages/review/scripts/final_portfolio.py --targets A B
信号回溯 → python 01-功能包-packages/review/scripts/final_review.py --target <NAME>
```

Skill 包内把路径换成 `python3 scripts/<同名入口>.py ...`。完整命令映射与自然触发词见 `AGENTS_DEEP.md`。

---

## 微信红线（CRITICAL）

推送到微信时禁止：`#` 标题、`---` 水平线、`**` 粗体、`|` 表格、`>` 引用、`*/-` 列表符。  
分节用 emoji 行（如 `🧭 中线`）。单票首行：`分析报告 — {名}（{码}）｜短中线`。  
全文见 `01-功能包-packages/_common/agent-rules.md`；满分范例见 `AGENTS_DEEP.md`「微信端满分输出范例」。

---

## 趋势与退出（摘要）

- 年线下方：`ma250_warning=True`，继续分析（不否决）
- ATR 移动止损：只紧不松（`structure_core`）
- 假跌破 + 分阶段退出 / fusion 覆盖：`decision_core.status_layers`
- 细节与配置项：`AGENTS_DEEP.md`

---

## 持久化文件

| 文件 | 用途 |
|------|------|
| `~/.trader/signals.jsonl` | Signal Contract v2 事件流 |
| `~/.trader/pool.json` / `pending.json` / `last_plan.json` | 选股池 |
| `~/.trader/calibrated_params.json` | 自校准参数 |
| `~/.trader/chip_history.json` | 筹码搬家快照 |
| `~/.t0-trader/state.json` / `~/.review-trader/state.json` | 技能缓存 |

完整读写表见 `AGENTS_DEEP.md`。

---

## 自检与验证

```bash
scripts/run-gate-tests.sh
python3 -m pytest 02-共享模块-shared/tests/
python3 02-共享模块-shared/scripts/pack_all.py
```

---

## 深度参考

| 需要了解 | 去哪里找 |
|---------|----------|
| 架构 / 算法 / 满分示例 | `AGENTS_DEEP.md` |
| Skill 契约 | 各 `SKILL.md` + `references/` |
| 输出格式 | `output-template.md` / `output-style-guide.md` |
| 测试 | `02-共享模块-shared/tests/TESTING.md` |
| 包 import | `from trader_shared.xxx import ...`；`pip install -e .` |
