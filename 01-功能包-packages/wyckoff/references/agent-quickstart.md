# Wyckoff Agent 快路径

目标：1 条命令 → code fence 原样贴出威科夫 B·中剪卡或池链排序 → 停。禁止先批量读 references。  
硬规则：同目录 `agent-rules.md`。  
默认 B·中剪卡；旧完整详析加 `--full`；短卡加 `--brief`。默认首行为 `{名}（{码}）｜现价 {price}`，标题下固定 `周线：` / `日线本波：` / `入池：` 三行；周线与日线块均为满灯竖排，短推演固定保留；推演「现在」附周/日量度（仅 L3 出目标，否则「未达 L3，暂不测算」）。failed 人话三档同源：写 `Phase A 失效`（禁 `Phase A 失败` / `已失效` / `旧故事作废`）；`--full`/`--brief` 仅对齐人话，不改骨架。

## 默认（cwd = 本 skill 根）

```bash
python3 scripts/final_wyckoff.py --target <NAME>
```

旧完整详析：

```bash
python3 scripts/final_wyckoff.py --target <NAME> --full
```

旧版短卡：

```bash
python3 scripts/final_wyckoff.py --target <NAME> --brief
```

池内吸筹链排序（读 `~/.trader/pool.json` 缓存）：

```bash
python3 scripts/final_wyckoff.py rank
```

- 成功：stdout 整段 code fence 贴出 → Exit
- 禁止改写、手写面板、把链进度写成「可执行/宜买/该买了」
- 禁止默认 `--output json`
- 失败：只报失败原因；禁止凭记忆补事件/阶段

## 硬门控

1. 未跑脚本 → 不报威科夫结论
2. 产品定位：人读结构卡，不是自动下单指令
3. 本 Skill 的 rank ≠ trader 分道
4. 遵守 `agent-rules.md` 微信红线（脚本已渲染则勿再排版）

## JSON 回退（仅渲染失败时）

才用 `--output json`；结论必须能指到脚本字段。

## 按需文档（勿预读）

| 何时 | 读什么 |
|------|--------|
| 格式校验 | `output-template.md` |
| 命令全集 | 本文件即可 |

## Exit

输出完成后即停止。
