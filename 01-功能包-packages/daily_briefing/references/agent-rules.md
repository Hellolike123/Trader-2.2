# Agent 共用硬规则（SSOT）

五 Skill（trader / t0 / review / wyckoff / daily_briefing）共用。改红线只改本文件；各 skill `references/agent-rules.md` 由本文件同步（或 `pack_all` 复制）。

## 执行契约（CRITICAL）

本 skill 是**命令包装器**，不是分析知识库。

1. 只预读该 skill 的 `references/agent-quickstart.md`
2. 跑入口脚本，默认渲染输出（markdown）
3. stdout **原样贴出**（整段放进 fenced code block）→ 停
4. 禁止开工前批量读 references
5. **禁止默认 `--output json`**（整包可达数百 KB）；仅 markdown 失败或确需字段时再开 JSON
6. **禁止**改写、摘要、润色、补买卖建议、补脚本未写的价位/阶段/出手
7. **脚本未成功产出面板** → 只报失败/降级原因；**禁止**凭记忆或训练数据编完整报告
8. markdown 成功时**不要读** `anti-hallucination.md` / 字段指南（那些只服务 JSON 回退）

## 微信 / 移动端红线

最终面板会进微信。贴出脚本面板时禁止改写成：

- `#` / `##` 等 Markdown 标题
- `---` / `***` 水平线
- `**` 粗体
- `|...|` 表格（并列用全角 `｜` 或空格）
- `>` 块引用
- `*` / `-` 列表符与带圈数字

分节用 emoji + 普通文本独立成行（如 `🧭 中线`、`⚡ 短线`）。
脚本已按红线渲染时：原样贴即可，不要「再排版」。

## 命令 cwd

- Skill 包内（Hermes / 已 cd 到 skill 根）：一律 `python3 scripts/<入口>.py ...`
- 仓库根（Cursor always-on）：`python3 01-功能包-packages/<skill>/scripts/<入口>.py ...`
- 仓位轮动在 **review** 包：`scripts/final_portfolio.py`（无独立 `portfolio/` 包）

## 按文档改代码（CRITICAL）

改引擎/合同（非贴面板快路径）时：先读 `BUSINESS.md` + 对应 `docs/plans/*-handoff.md`，禁止凭感觉发明行为。合同级改动默认「写 Agent + 查 Agent」对照法源验收后再 PR。全文见仓库根 `AGENTS.md`「按文档开发」与 `.cursor/rules/doc-driven-dev.mdc`。

## 防漏改清单（改代码时）

改单票报告格式时固定步骤（勿改 legacy / 勿手改 AGENTS 满分示例数字）：

1. 改 `trader_shared/report_renderer/short_midline.py`
2. 刷新 `02-共享模块-shared/tests/golden/*.render.md` + `fixtures/report_render_baseline.txt`
3. 分区骨架变了再同步 `trader/references/output-template.md`（门禁会查分区头）
4. 契约/业务同步：`BUSINESS.md` §5.1（及涉及的 §3.x）+ `AGENTS_DEEP.md` 微信满分骨架 + `output-style-guide.md`

顶栏（现行）：`环境：{宽基} ±% ｜ {主交易板块?} ±% ｜ 强于/弱于/持平板块` → `概念：标签…`（身份，禁止概念假指数）→ `量能：量比/换手/调整/动能/ATR14`。禁止再写「大盘 正常/偏弱」或单独「行业：…｜跑赢…」行；动能不进环境行。

短线学说点名：中线/短线均写 `威科夫：`。中线=周线大侧；短线=日线短波（先定吸筹/派发侧再写主灯，如 `短波派发 · LPSY偏空@x · 不作买点`；事件并入同行；尾注「不作买点」）。中短线标题挂灯：`🧭 中线｜🔴 防守` / `⚡ 短线｜🔴 不新开`（🟡观望/仅观察，🟢可跟踪/去看trader；绿=资格非可买；不写「操作灯」）。**禁止**面板标签 `日线阶段：` / 独立 `事件：` / `定论：`。箱体人话：`箱体 lo-hi` / `箱体未成形 · 下沿…（上沿未出）`（禁写旧词「区间未钉」作产出）。

| 改什么 | 认准一处 |
|--------|----------|
| 中短线面板文案 | 上面步骤 |
| 板块对照指数 / 环境档 | `market_env.resolve_board_index` + `assess(index_code=)`；接线 `context_stage` |
| 新开 / 出手收紧 | `chan_discipline` / `mistery_gate` / `decision_view`（须 entry.executable；C1 用 `format_entry_line_c1`；禁止新开时 caps/`suggested_pct` 归零） |
| Fusion 席位（生产） | `analysis/fusion_card_signals.py`（cards 路径；失败 → `cards_failed` 中性，禁静默 classic） |
| ATR 移动止损水位 | `structure_core`（持仓票 `~/.trader/trailing_stop_watermark.json`，只紧不松） |
| 买点盖价 | `buy_point_lifecycle.resolve_lid_price`（显式>回踩下沿>买区下沿>支撑；不用 life_line 当回踩） |
| 微信红线本身 | 只改本文件，再 sync 各 Skill 的 `references/agent-rules.md` |

生产唯一渲染：短中线（`SHORT_MIDLINE_REPORT=false` 已忽略）。Fusion 默认 `cards`；`classic`/`compare` **已退役**（设了也告警后仍走 cards）。出手听 `decision_view`（entry 须 executable），fusion 分仅仪表；`FUSION_OVERRIDE_ENABLED` 默认 false。
