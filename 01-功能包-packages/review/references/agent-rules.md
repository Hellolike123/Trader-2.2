# Agent 共用硬规则（SSOT）

四 Skill（trader / t0 / review / wyckoff）共用。改红线只改本文件；各 skill `references/agent-rules.md` 由本文件同步（或 `pack_all` 复制）。

## 快路径

1. 只预读该 skill 的 `references/agent-quickstart.md`
2. 跑入口脚本，默认渲染输出（markdown）
3. stdout **原样贴出** → 停
4. 禁止开工前批量读 references
5. **禁止默认 `--output json`**（整包可达数百 KB）；仅 markdown 失败或确需字段时再开 JSON

## 微信 / 移动端红线

最终面板会进微信。生成或转述输出时禁止：

- `#` / `##` 等 Markdown 标题
- `---` / `***` 水平线
- `**` 粗体
- `|...|` 表格（并列用全角 `｜` 或空格）
- `>` 块引用
- `*` / `-` 列表符与带圈数字

分节用 emoji + 普通文本独立成行（如 `🧭 中线`、`⚡ 短线`）。

## 命令 cwd

- Skill 包内（Hermes / 已 cd 到 skill 根）：一律 `python3 scripts/<入口>.py ...`
- 仓库根（Cursor always-on）：`python3 01-功能包-packages/<skill>/scripts/<入口>.py ...`
- 仓位轮动在 **review** 包：`scripts/final_portfolio.py`（无独立 `portfolio/` 包）

## 防漏改清单（改代码时）

改单票报告格式时固定三步（勿改 legacy / 勿手改 AGENTS 满分示例）：

1. 改 `trader_shared/report_renderer/short_midline.py`
2. 刷新 `02-共享模块-shared/tests/golden/*.render.md`
3. 分区骨架变了再同步 `trader/references/output-template.md`（门禁会查分区头）

| 改什么 | 认准一处 |
|--------|----------|
| 中短线面板文案 | 上面三步 |
| 新开 / 出手收紧 | `chan_discipline` / `mistery_gate` / `decision_view`（须 entry.executable；C1 用 `format_entry_line_c1`；禁止新开时 caps/`suggested_pct` 归零） |
| Fusion 席位（生产） | `analysis/fusion_card_signals.py`（cards 路径；失败 warning→classic） |
| ATR 移动止损水位 | `structure_core`（持仓票 `~/.trader/trailing_stop_watermark.json`，只紧不松） |
| 买点盖价 | `buy_point_lifecycle.resolve_lid_price`（显式>回踩下沿>买区下沿>支撑；不用 life_line 当回踩） |
| 微信红线本身 | 只改本文件，再 sync 三 Skill 的 `references/agent-rules.md` |

生产唯一渲染：短中线（`SHORT_MIDLINE_REPORT=false` 已忽略）。Fusion 默认 `cards`；classic 仅对照（deprecated）。出手听 `decision_view`（entry 须 executable），fusion 分仅仪表；`FUSION_OVERRIDE_ENABLED` 默认 false。
