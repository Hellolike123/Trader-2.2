# Skill 合并方案

## 背景

当前 6 个 skill 存在以下问题：
- 骨架重复（6 套 SKILL.md / HERMES.md / commands.md / output-contract.md）
- 紧耦合（pool 直接 import trader 的 run_analysis）
- 边界模糊（pool 和 trader 都有 run_analysis.py）
- 80% 的提交是跨 skill 的，改一个功能要同步多个目录
- 维护成本高，使用记不住

## 决策：6 合 3

```
原 6 个 skill                    合并后 3 个
─────────────                   ──────────────
01-单票分析-trader        ──┐
03-选股池-trader-pool     ──┼──▶  trader（分析+选票）
                            │
02-盘中T0-t0-trader       ──┼──▶  t0（盘中盯盘）
                            │
04-仓位轮动-trader-portfolio──┤
05-盘后复盘-review-trader  ──┼──▶  review（盘后复盘+仓位+追踪）
06-信号追踪-trader-tracking──┘
```

## 各 Skill 职责

### trader（分析+选票）

职责：单票分析 + 选股池管理
- 单票分析报告（原 01-trader）
- 选股池入池/出池/排序/作战表（原 03-pool）
- 买 zone + 止损计算

命令映射：
- `trader script --target <NAME>` → 单票分析
- `trader script add --target <NAME>` → 入池
- `trader script rank` → 池内排序
- `trader script plan` → 作战表
- `trader script remove --target <NAME>` → 出池

### t0（盘中盯盘）

职责：实时监控 + 告警（变薄，只负责「看」和「响」）
- 盘中大单异动扫描（原 02-t0）
- 价格到位告警
- 读 trader 的 pool.json 知道盯哪几只
- 触发后写 signals.jsonl

命令映射：
- `t0 script --target <NAME>` → 单次检查
- `t0 script --target <NAME> --monitor` → 持续监控
- `t0 script --target <NAME> --monitor --once` → 定时任务单次

### review（盘后复盘+仓位+追踪）

职责：盘后复盘 + 仓位轮动 + 信号统计分析
- 五层打分复盘（原 05-review）
- 仓位轮动（原 04-portfolio）
- 信号统计分析（原 06-tracking，重新设计）

命令映射：
- `review script --target <NAME>` → 单票复盘
- `review script --targets A B` → 仓位轮动
- `review script --tracking` → 信号统计分析

## 信号统计分析（原 tracking）

重新设计的输出格式，定位：「信号说买→涨了吗？信号说卖→跌了吗？」

不给建议，只给数字，用户自己判断。

```
🎯 信号统计分析
══════════════════════════════════

最近 30 天 ｜ 38 次信号

说买 → 涨了    23/38  61%
说卖 → 跌了     5/6   83%

📊 信号类型

低吸观察  说买 → 涨    13/20  65%
突破确认  说买 → 涨     5/12  42%
防守观察  说卖 → 跌     4/5   80%

📌 个股

南网科技  说买 → 涨     4/5   80%
中国铝业  说买 → 涨     1/3   33%
紫金矿业  说买 → 涨     3/4   75%

📈 趋势

本月 61%  上月 55%  ↑ 在变好
```

## 数据流

```
trader ──writes──▶ pool.json ──reads──▶ t0
  │                                       │
  │                                  writes signals.jsonl
  │                                       │
  └────reads────▶ signals.jsonl ◀─────────┘
                       │
                       ▼
                   review ──writes──▶ signal_results.jsonl
```

## 输出格式规范

三个 skill 统一遵循微信端格式红线：
- 禁用 # 标题，用 emoji + 普通文本
- 禁用 --- 水平线
- 禁用 ** 粗体
- 禁用 |...| 表格
- 禁用 > 块引用
- 禁用 - / * 列表符
- 首行固定 emoji + 标题

### trader 输出

```
分析报告 — 南网科技（688248）

现价：59.33元（+2.70%）
MA5：59.63 ｜ MA10：60.74 ｜ MA20：60.60 ｜ MA30：59.72

🧭 简要分析
基础状态：防守观察 ｜ 体系结论：防守观察

📍 决策
状态：防守观察
  空仓：在 57.50-58.64元 试探买 5%, 止损 56.11
  有底仓：反弹 59.84 冲不动就减 10-20%

❗ 关键价位
56.11  ← 止损位
57.50  ← 防守位
59.33  ← 当前位置
59.84  ← 确认位
```

### t0 输出

```
🎯 T0 盯盘助理
南网科技（688248）｜现价 59.33（+2.70%）

🔍 扫描
当前：不动
买入：不动，观察 57.50
卖出：不动，观察 59.84

🚩 关键价位
低吸观察：57.50 ｜ 高抛观察：59.84
止损：56.11

👀 下一步只盯
买入：57.50
卖出：59.84
止损：56.11
```

### review 输出

```
📌 南网科技｜2026-05-28 盘后复盘
收盘 59.33（+2.70%）

结论：弱修复观察，不能按反转处理

📊 关键价位
支撑：58.44 ｜ 压力：60.26 ｜ 止损：56.11

📈 五层打分
结构65 量价45 筹码50 动能50

👉 一句话
明天放量站稳 60.26 才算确认
```

## 迁移步骤

1. 创建新的 3 个 skill 目录结构
2. 迁移代码到对应目录
3. 统一 SKILL.md / commands.md / output-contract.md
4. 重写 pack_all.py 支持新结构
5. 迁移 pool 的 import 依赖（trader-pool → trader）
6. 迁移 portfolio + tracking 到 review
7. 验证所有命令正常工作
8. 删除旧的 6 个 skill 目录

## 依赖关系

```
trader_shared（不变）
  ├── trader（分析+选票）
  │     └── run_analysis.py（核心分析引擎）
  ├── t0（盯盘）
  │     └── 读 pool.json
  └── review（复盘+仓位+追踪）
        └── 读 signals.jsonl + signal_results.jsonl
```

pool 原来直接 import trader 的 run_analysis，合并后变成同一 skill 内部调用，耦合问题自动消除。
