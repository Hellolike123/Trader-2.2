# 样本干跑验票（池空兜底）— Agent Handoff

> **状态**: done（2026-08-02；写/查双 Agent PASS，池空+四样本）  
> **轨道**: 与「缠论观察档」并行（用户口令：1 真池干跑）  
> **说明**: 云环境 `~/.trader/pool.json` 常为空 → **用固定样本票**等价干跑；池命令诚实报空即可。  
> **产品裁决**: **只读验票 + 写 SUMMARY**；默认不改引擎。发现合同违反 → 记入 SUMMARY「must-fix」，由父 Agent 另开修 PR（本轨道不顺便大改）。

---

## 1. 样本与命令

样本至少：

1. 南网储能（或南网科技）  
2. 中国船舶  
3. 宁德时代  
4. 上证指数  

命令（仓库根，exit 与 stdout 均保留）：

```bash
python3 01-功能包-packages/trader/scripts/final_pool.py rank
python3 01-功能包-packages/wyckoff/scripts/final_wyckoff.py rank
python3 01-功能包-packages/wyckoff/scripts/final_wyckoff.py --target <NAME>
python3 01-功能包-packages/trader/scripts/final_report.py --target <NAME>
python3 01-功能包-packages/chanlun/scripts/final_chanlun.py --target <NAME>
```

面板落盘：`/tmp/cursor/smoke-dual/<name>_{wyckoff,report,chanlun}.md`  
总表：`/tmp/cursor/smoke-dual/SUMMARY.md`

---

## 2. 验收对照（写 Agent 自检 + 查 Agent 复核）

法源：

- 威科夫失效文案：`wyckoff-phase-fail-copy-handoff.md` / fail-copy-cleanup / report-fail-copy-leak / phase-label-sanitize  
- L0 无假箱：`wyckoff-tr-maturity-l0l3-handoff.md`  
- 缠论四关心点：`chanlun-skill-playbook.md` §0；deep-card C-D*（已合部分）  
- 微信红线：`_common/agent-rules.md`

禁词（面板可见）：`旧底已废` / `废锚` / `Phase A failed` / `（已废）` / `待新寻底` / `Phase A失败` / `Phase A 失败` / `舞台` / `换幕`（主展示）/ 下单词 `宜买|可执行|可低吸|该买了`

其它：

| 项 | 期望 |
|----|------|
| 中国船舶日线 L0 | 「无箱」类，无假雏形箱价 |
| 上证指数 | 不得落到平安银行价位；价位应像指数 |
| 缠论笔 | 当前笔方向与近笔序列自洽；无手补买卖点 |
| 池空 | rank 诚实提示，不伪造池 |

---

## 3. 禁止

1. 本轨道不改业务代码（除非脚本无法 import——只记问题）。  
2. 不发明新出手逻辑。  
3. 不把 SUMMARY 数字改写成「更好看」。

---

## 4. 双 Agent

- **写 Agent**：跑命令、落盘、写 SUMMARY（含逐票 ✅/❌ 与总 verdict）。分支可仍在 main 工作区只读；**不要 commit 业务**。  
- **查 Agent**：只读 SUMMARY + 抽样面板，对照 §2 列 must-fix；总 verdict PASS/FAIL。
