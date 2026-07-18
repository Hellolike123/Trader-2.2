# 分层落地计划与测试清单

> **状态**：执行计划  
> **版本**：v0.1 · 2026-07-18  
> **架构**：`strategy-layered-architecture.md`  
> **包契约**：`strategy-pack.md`

---

## 1. 节奏总览

| 阶段 | 主题 | 产出 | 完成定义（含测试） |
|------|------|------|-------------------|
| **P0** | 分析契约 | 意见卡字段表；可单独读威/缠 | 契约文档 + 字段存在性/边界单测 |
| **P1** | 闸口契约 | 6 闸口 IO + 互斥（可无代码） | 文档评审通过 |
| **P2** | 策略最小集 | G/E + entry 一包 + manage A 预案 + stop 全清 | `test_strategy_match` 绿 + 真票 1 只 |
| **P3** | 报告 📐 | 闸口展示；plan vs active | 渲染单测 + 微信红线检查 |
| **P4** | 扩展 | take F、scale、多 entry B/C/D | 互斥回归 + 真票 |

原则：

- 先理论/分析稳，再策略，再打磨报告细文案（骨架可在 P1 预留）  
- 每闸最多 1 主用包  
- 门禁测试默认 **无网、确定性**

---

## 2. P0 · 分析层（当前主攻）

### 2.1 任务

1. 冻结意见卡键名（chan / wyckoff / momentum / chip / 公共）  
2. 对齐现有 `format_*` / View 与字段表  
3. Skill：可只问威科夫状态（读 midline/daily 卡）  
4. 口径决策（改代码或只改文档，二选一写死）：  
   - 单日跌幅熔断：`<= -7%` 还是 `< -7%`  
   - VPF 资金强信号 vs 天量空：谁优先  

### 2.2 测试

| ID | 用例 | 期望 |
|----|------|------|
| A-01 | wyckoff weekly 无 TR | phase none；文案「周线已算/定不出」类，非静默空 |
| A-02 | wyckoff event Spring | event 卡非空；midline/short light 含灯 |
| A-03 | chan 一类买 | buy_type 可解析；short light 类型优先 |
| A-04 | chip 无峰无 pct | 不输出噪声行或明确空 |
| A-05 | chip 跌穿成本 | 支撑弱 · 阻力 · 套牢面（方案 C） |
| A-06 | 意见卡无 NaN/Inf | 数值字段有限 |

命令示例：

```bash
export PYTHONPATH=02-共享模块-shared
python3 -m pytest 02-共享模块-shared/tests/test_wyckoff_core.py \
  02-共享模块-shared/tests/test_chanlun_correctness.py \
  02-共享模块-shared/tests/test_report_optimization.py -q
```

### 2.3 DoD

- [ ] `docs/designs/` 意见卡表与代码键一致  
- [ ] 上表 A-01～A-06 有对应测或明确 skip 原因  
- [ ] 7% / VPF 口径写入 BUSINESS 或本文 §6  

---

## 3. P1 · 闸口契约（可先无代码）

### 3.1 任务

- 每个闸口：输入字段、输出字段、`mode`  
- 互斥表（architecture §3.1）  
- 包命名规范：`select.*` / `entry.*` / …

### 3.2 测试（文档验收）

| ID | 检查 |
|----|------|
| G-01 | 六闸口均有「只回答什么」 |
| G-02 | stop 全清写进契约 |
| G-03 | 未持仓 / 已持仓行为分开 |
| G-04 | G/E 否决 entry 执行 |

### 3.3 DoD

- [ ] 契约表合入 architecture，无歧义  

---

## 4. P2 · 策略最小实现

### 4.1 任务

1. `strategy_match.py`：纯函数，输入 report-like dict  
2. 包 YAML 最小集：`select.observe_G` / `select.defense_E` / `entry.chan_buy1_probe` / `manage.wyckoff_trail`  
3. bind：stop/floor 从现有 support/stop 填数  
4. 不接实盘下单  

### 4.2 测试（必写）

| ID | given | then |
|----|-------|------|
| S-01 | action 不新开，无持仓 | entry.mode=plan 或 off；不得 active 买入文案 |
| S-02 | SOW + 支撑弱 | defense_E 或 observe 优先于 entry active |
| S-03 | 一买 + 清单未全绿 | 与纪律一致：不可「可试探执行」 |
| S-04 | has_position + floor | manage 给出 stop_price；policy 含全清 |
| S-05 | 无 cost | 不得进入 S2 保本阶段 |
| S-06 | 两 entry 都 match | 仅 1 primary（priority） |

```bash
python3 -m pytest 02-共享模块-shared/tests/test_strategy_match.py -q
```

### 4.3 DoD

- [ ] S-01～S-06 全绿  
- [ ] 真票 1 只：人工确认 📐 主用合理  

---

## 5. P3 · 报告展示

### 5.1 任务

- `render_short_midline` 增加 📐 闸口区  
- plan / active 文案区分  
- 不破坏微信红线  

### 5.2 测试

| ID | 检查 |
|----|------|
| R-01 | 报告含 `📐` 或约定等价标题 |
| R-02 | 不新开时无「已持仓执行」误导句 |
| R-03 | 无 `#` `**` `\|...\|` 表格 `---` |
| R-04 | 与 golden/快照策略（若启用）一致或有意 recapture |

### 5.3 DoD

- [ ] R-01～R-03 自动化  
- [ ] 南网 + 三花人工读一遍  

---

## 6. P4 · 扩展

- take.partial_F、scale 条件、entry C/D  
- 回归：S-01～S-06 + 新包互斥  
- 禁止重新引入「万能包」  

---

## 7. 已知计算口径（分析层债务）

| 项 | 现状 | 建议 |
|----|------|------|
| 单日 -7% 熔断 | 代码 `change < -7`（刚好 -7 不触发） | 产品定 `<=` 或改测 |
| VPF 冲突 | 资金 conf≥0.55 可压过价量空 | 定 climactic 例外或改测 |
| 周线威无 TR | 定不出阶段 | 保持诚实文案 |
| main_force 解析测试 | 旧 API import 失败 | 修测或删 |

**不阻塞** P1 文档；**建议在 P0 标口径**，改代码另开任务。

---

## 8. 命令备忘

```bash
export PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts

# 分析相关
python3 -m pytest 02-共享模块-shared/tests/test_fusion_core.py \
  02-共享模块-shared/tests/test_wyckoff_core.py \
  02-共享模块-shared/tests/test_chanlun_correctness.py -q

# 策略（P2 后）
python3 -m pytest 02-共享模块-shared/tests/test_strategy_match.py -q

# 真票
python3 01-功能包-packages/trader/scripts/final_report.py --target 002050 --output markdown
```

---

## 9. 与桌面旧稿

原桌面讨论稿《Trader策略包设计》《思路总结》内容已吸收进：

- `strategy-layered-architecture.md`  
- `strategy-pack.md`  
- 本文  
- （可选）`strategy-menu.md`  

**以仓库 `docs/designs/` 为准。**

---

*每完成一阶段，更新本文勾选 DoD，并视需要 bump 版本号。*
