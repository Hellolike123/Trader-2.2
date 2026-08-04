# Roster 提案（等人批 — silence ≠ approval）

探测命令本会话未能执行：

```bash
python3 ~/.agents/skills/sop/scripts/discover-roster.py --probe \
  --out workflows/sos-single-day-fix/roster.json
```

在 probe 补跑前，按**条件**暂拟（可一票否决）：

```
roster:   probe 未跑（bash 拒）→ 条件分配 + 人工确认
orchestrator: 本会话 Cindy（用户正在对话的 agent）
sole-writer:  本会话 Cindy / pi（唯一写权；Medium 可接受）
               若你希望更强 frontier：批「writer=claude|codex」后改派
reviewer:     优先跨厂商独立只读会话
               推荐：codex（openai）只读 review  ← 若本机可用
               降级 ladder：
                 1) 跨厂商 ✓
                 2) 同厂商不同 tier
                 3) 同模型新鲜只读会话（Medium 允许；Data/destructive 禁止）
scouts:       可选跳过（research 已由 orchestrator 只读完成）
gates:        实现前门：计划批准
              实现后：reviewer PASS → 再谈 commit/PR（本任务默认不 deploy）
repo:         /Users/like/Documents/Opencode/Trader3.0
```

**请回复其一：**

1. `roster ok` — 接受上表（writer=本会话，reviewer 实现后另开跨厂商只读）
2. `roster ok writer=claude reviewer=codex` — 或你指定的组合
3. `roster veto: ...` — 说明改法

批准前**不**改业务代码、不写正式 handoff 以外的实现。
