# Agent 共用硬规则（SSOT）

四 Skill（trader / t0 / review / wyckoff）共用。改红线只改 `_common/agent-rules.md`；各 skill `references/agent-rules.md` 由该文件同步（或 `pack_all` 复制）。

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

分节用 emoji + 普通文本独立成行（如 `🧭 阶段`、`📎 链`）。

## 命令 cwd

- Skill 包内（Hermes / 已 cd 到 skill 根）：一律 `python3 scripts/<入口>.py ...`
- 仓库根（Cursor always-on）：`python3 01-功能包-packages/<skill>/scripts/<入口>.py ...`
- 仓位轮动在 **review** 包：`scripts/final_portfolio.py`（无独立 `portfolio/` 包）

## 威科夫 Skill 补充

- 人读结构卡，不作交易总司令
- `rank` 仅链视角排序，不改 trader 分道
- 禁止「可执行 / 宜买 / 可低吸 / 三重共振买」
