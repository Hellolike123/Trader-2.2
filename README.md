# Trader3.0 — A 股量化分析系统

> 输入一只 A 股代码 → 输出多维度分析报告（短中线双轨）。

## 核心能力

- **三策略融合**：缠论 + 动量 + 价量资金，三评委加权决策（正常大势动量权重 0.45 / 缠论 0.30）
- **四阶段定位**：蓄势 / 主升 / 派发 / 衰退（出手听 decision_view；fusion.weighted_score 仅仪表）
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
├── AGENTS.md                   ← Agent 入口（含「改代码去哪」）
├── AGENTS_DEEP.md              ← 算法 / 满分示例 / 深度契约
├── BUSINESS.md                 ← 业务逻辑
├── README.md                   ← 本文件
│
├── 02-共享模块-shared/         ← 核心共享库（引擎真相）
│   ├── trader_shared/
│   │   ├── report_builder.py   ← 单票编排（只排队）
│   │   ├── report_pipeline/    ← 流水线各 stage
│   │   ├── fusion_core.py      ← 融合（生产 = cards）
│   │   ├── t0_*.py             ← T0 引擎
│   │   ├── review_*.py / portfolio_*.py
│   │   ├── plugins/            ← 分析插件
│   │   └── config.py
│   └── tests/
│
├── 01-功能包-packages/         ← Skill CLI + shim
│   ├── _common/agent-rules.md
│   ├── trader/scripts/
│   │   ├── final_report.py     ← 单票分析入口
│   │   ├── final_pool.py       ← 选股池薄入口
│   │   └── pool_cmds/          ← 选股池实现
│   ├── t0/scripts/             ← final_t0 + identity shim → trader_shared
│   └── review/scripts/         ← final_review / portfolio + shim
│
├── scripts/                    ← 项目级脚本
│   ├── run-gate-tests.sh       ← CI 门禁
│   └── golden_diff_gate.py
│
└── docs/designs/               ← 法源（含 resonance-and-orchestration.md）
```

改实现优先读 `AGENTS.md`「改代码去哪」，不要在 skill shim 里复制引擎。

## 文档体系

| 文档 | 读者 | 内容 |
|------|------|------|
| **AGENTS.md** | AI Agent | 快路径 + 改代码地图 + 红线摘要 |
| **AGENTS_DEEP.md** | 开发者 / Agent | 算法细节、满分示例、深度契约 |
| **docs/designs/resonance-and-orchestration.md** | Agent | 五层+编排法源 |
| **BUSINESS.md** | 开发者 / 业务人员 | 业务逻辑、计算规则、报告规则 |
| **README.md** | 所有人 | 项目简介、快速开始 |

## 技术栈

- **语言**：Python 3.11+
- **数据源**：腾讯 / 新浪 / mootdx / akshare / Tushare
- **测试**：pytest + `scripts/run-gate-tests.sh`
- **CI**：pre-push hook → golden diff gate

## 开发方式

1. **阅读**：`AGENTS.md`（含「改代码去哪」）→ 法源 `docs/designs/resonance-and-orchestration.md` → 按需 `AGENTS_DEEP.md` / `BUSINESS.md`；冲突以 `trader_shared/` 代码为准。旧 `AGENT.md` 已降级，勿当主入口。
2. **开发**：引擎改 `trader_shared/`；选股池改 `pool_cmds/`；skill 包内同名脚本多为 shim
3. **测试**：`bash scripts/run-gate-tests.sh`
4. **推送**：`git push`（自动触发门禁）
