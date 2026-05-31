## 1. Trader JSON 输出

- [x] 1.1 修改 `final_report.py`，`--output json` 直接输出 report dict 的 JSON（替换现有的 `{"full_markdown": ..., "report": ..., "signal": ...}` 包装格式）
- [x] 1.2 在 `run_analysis.py` 的 `build_report()` 中补全 `one_liner` 字段（调用 `one_sentence()` 存入 report dict）
- [x] 1.3 在 `build_report()` 中补全 `t0_ref` 字段（从 levels 计算 low_buy/high_sell/stop 存入 report dict）
- [x] 1.4 在 `build_report()` 中补全 `macd_status` 字段（从 momentum_strategy 结果提取 MACD 方向存入 report dict）
- [x] 1.5 验证：执行 `python3 final_report.py --target 688248 --output json` 输出有效 JSON，包含全部 63+ 个字段

## 2. T0 JSON 输出

- [x] 2.1 在 `t0_core.py` 或 `t0_run.py` 中新增 `--output json` 参数支持（已存在）
- [x] 2.2 JSON 输出包含核心字段：current_price、today_action、buy（status/observation_price/trigger_price/invalid_price）、sell（同结构）、volume_ratio、vwap、atr_info、data_status（已存在）
- [x] 2.3 JSON 输出包含 big_orders 列表（已存在）
- [x] 2.4 验证：执行 t0 script --target 688248 --once --output json 输出有效 JSON

## 3. Review JSON 输出

- [x] 3.1 在 `review_render.py` 或 `review_single.py` 中新增 `--output json` 参数支持（已存在）
- [x] 3.2 JSON 输出包含核心字段：quote、cost、pnl_pct、conclusion_text、one_liner_text、theory（scores/supports/blocks）、levels、big_order、macd_params、atr、chip_distribution、summary（已存在）
- [x] 3.3 验证：执行 review script --target 688248 --output json 输出有效 JSON

## 4. SKILL.md 重写

- [x] 4.1 重写 `~/.hermes/skills/trader/SKILL.md`，包含：我是谁、怎么调命令、怎么读数据、三步 Pipeline、解读框架、Inversion 澄清规则、Reviewer 防幻觉清单
- [x] 4.2 重写 `~/.hermes/skills/t0/SKILL.md`，包含同样结构（适配 t0 场景）
- [x] 4.3 重写 `~/.hermes/skills/review/SKILL.md`，包含同样结构（适配 review 场景）
- [x] 4.4 三个 SKILL.md 中明确写"必须调 --output json，禁止从 Markdown 解析数据做判断"

## 5. AI Guide 文件

- [x] 5.1 创建 `~/.hermes/skills/trader/references/ai-guide.md`，包含 trader JSON 全部字段的名称、类型、含义、示例值
- [x] 5.2 创建 `~/.hermes/skills/t0/references/ai-guide.md`，包含 t0 JSON 全部字段说明
- [x] 5.3 创建 `~/.hermes/skills/review/references/ai-guide.md`，包含 review JSON 全部字段说明
- [x] 5.4 三个 ai-guide.md 中标注"核心字段"（AI 必读）和"可选字段"（按需读）

## 6. HERMES.md 输出规则更新

- [x] 6.1 修改 `~/.hermes/skills/trader/HERMES.md`，将"脚本输出即最终格式，不要修改"改为双模式规则（给人看原样转发，给 AI 用读 JSON 做解读）
- [x] 6.2 修改 `~/.hermes/skills/t0/HERMES.md`，同样改为双模式规则
- [x] 6.3 修改 `~/.hermes/skills/review/HERMES.md`，同样改为双模式规则
- [x] 6.4 三个 HERMES.md 中明确写"禁止从 Markdown 输出解析数据做判断"

## 7. 测试

- [x] 7.1 验证 trader --output json 输出的 JSON 可被 Python json.loads() 解析
- [x] 7.2 验证 t0 --once --output json 输出的 JSON 可被解析
- [x] 7.3 验证 review --output json 输出的 JSON 可被解析
- [x] 7.4 验证现有 Markdown 输出不受影响（不加 --output json 时输出不变）
- [x] 7.5 验证 SKILL.md 格式符合 Google 5 模式结构
- [x] 7.6 验证三个 HERMES.md 已更新为双模式规则
