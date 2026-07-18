# Trader3.0 — A 股量化分析系统

> 输入一只 A 股代码 → 输出多维度分析报告（短中线双轨）。

## 核心能力

- **三策略融合**：缠论 + 动量 + 价量资金，三评委加权决策（正常大势动量权重 0.45 / 缠论 0.30）
- **四阶段定位**：蓄势 / 主升 / 派发 / 衰退（方向仍看 fusion.weighted_score）
- **双轨报告**：中线（周线威科夫+缠论，默认 260 周）+ 短线（日线三专家 + 纪律出手）
- **选股池管理**：三关筛选（阶段→评分→风控）
- **纪律门控**：出手 / 新开清单 / 仓位上限 / 失效
- **CI 门禁**：离线 pytest 门禁 + golden diff 闸门

## 快速开始

```bash
# 1. 设置环境
export PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts

# 2. 分析一只票
python 01-功能包-packages/trader/scripts/final_report.py --target 002050 --output markdown

# 3. 选股池管理
python 01-功能包-packages/trader/scripts/final_pool.py analyze --target 002050
python 01-功能包-packages/trader/scripts/final_pool.py list
python 01-功能包-packages/trader/scripts/final_pool.py plan

# 4. 跑测试
bash scripts/run-gate-tests.sh
```

## 目录结构

```
Trader3.0/
├── AGENT.md                    ← AI Agent 开发宪法（最高规范）
├── ARCHITECTURE.md             ← 系统架构
├── BUSINESS.md                 ← 业务逻辑
├── README.md                   ← 本文件
│
├── 02-共享模块-shared/         ← 核心共享库
│   ├── trader_shared/          ← Python 包（核心共享库）
│   │   ├── report_builder.py   ← 总编排器
│   │   ├── fusion_core.py      ← 融合决策
│   │   ├── plugins/            ← 分析插件
│   │   ├── config.py           ← 全局配置
│   │   └── testing/            ← 测试 mock
│   └── tests/                  ← 测试（~70 文件）
│
├── 01-功能包-packages/         ← CLI 入口
│   └── trader/scripts/
│       ├── final_report.py     ← 单票分析
│       ├── final_pool.py       ← 选股池
│       └── run_analysis.py     ← 分析执行器
│
├── scripts/                    ← 项目级脚本
│   ├── run-gate-tests.sh       ← CI 门禁
│   └── golden_diff_gate.py    ← Golden 闸门
│
└── docs/                       ← 设计文档 + ADR
```

## 文档体系

| 文档 | 读者 | 内容 |
|------|------|------|
| **AGENT.md** | AI Agent | 开发宪法：架构、流程、规范、速查 |
| **ARCHITECTURE.md** | 开发者 / Agent | 系统架构、模块清单、依赖关系 |
| **BUSINESS.md** | 开发者 / 业务人员 | 业务逻辑、计算规则、报告规则 |
| **README.md** | 所有人 | 项目简介、快速开始 |

## 技术栈

- **语言**：Python 3.11+
- **数据源**：腾讯 / 新浪 / mootdx / akshare / Tushare
- **测试**：pytest + `scripts/run-gate-tests.sh`
- **CI**：pre-push hook → golden diff gate

## 开发方式

1. **阅读**：`AGENT.md`（最高规范）→ `ARCHITECTURE.md` → `BUSINESS.md`；冲突以 `trader_shared/` 代码为准
2. **开发**：遵守分层架构 + 插件化
3. **测试**：`bash scripts/run-gate-tests.sh`
4. **推送**：`git push`（自动触发门禁）
