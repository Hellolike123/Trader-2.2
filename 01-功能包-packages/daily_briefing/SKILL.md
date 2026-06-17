# daily-briefing — AI 每日简报

## 我是谁
从大量候选池中自动分析、排序、分层，输出每只票的次日操作建议。

## 怎么调命令

| 需求 | 命令 |
|------|------|
| 刷新选股池 | `python3 scripts/briefing.py` |
| 只分析指定票 | `python3 scripts/briefing.py --watch A B C` |
| 分析候选文件 | `python3 scripts/briefing.py --candidates candidates.json` |
| 刷新全池数据 | `python3 scripts/briefing.py --refresh` |
| 快速分析并加入池 | `python3 scripts/briefing.py --candidate A --add` |
| JSON 输出 | `python3 scripts/briefing.py --json` |

## 输出格式

分层全显示：
- 🔥 执行区（可交易）
- 👀 观察区（只看不买）
- ⏳ 待补区（评分不足）
- 🚫 放弃区

每只显示：名称、总分、阶段、买卖区间、止损、操作建议

## 工作流程

Step 1: 收集标的（pool + candidates + watch）
Step 2: 并行分析（build_report）
Step 3: 评分排序（score_report）
Step 4: 分层（执行/观察/待补/放弃）
Step 5: 渲染输出

## 文件结构

```
daily_briefing/
├── SKILL.md
├── scripts/
│   ├── __init__.py
│   └── briefing.py       # 主入口
└── tests/
    └── test_briefing.py   # 单元测试
```
