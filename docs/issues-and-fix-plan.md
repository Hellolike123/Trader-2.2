> 最后更新：2026-05-10
> 变更：根据逐条代码审查 + 167-180 修复经验，修正 P0/P1 分类和修复策略

# Trader 项目问题排查与修复计划

## 总目标

找出最影响结果正确性的地方，优先修复导致：

- 信号错
- 结果错
- 显示误导
- 跨模块结论不一致

的问题。然后再统一命名、语义和数据流，最后再决定是否需���架构调整。

---

## 一、问题清单与当前状态

### P0 级：真 bug（已完成修复）

| # | 问题 | 状态 | 备注 |
|---|------|------|------|
| **1** | `pipeline.write()` 状态合并有污染风险 | ✅ 已修 | commit `454f4dc` — 修变量遮蔽，local state dict 不再覆盖全局 |
| **2** | `stable_id()` 太弱，同天同票同类型信号可能被压成同一条 | ✅ 已修 | commit `a27c338` — `stable_id(skill, target, date, signal_type, price)` 接受 price 参数，不同 trigger 价格生成不同 ID |
| **3** | `current_pct` 语义与实现不一致 | ✅ 已修 | commit 早期 — chip_distribution peaks 排名逻辑修正 |
| **4** | `cmd_watch()` 固定 2% 阈值 | ❌ 非修复项 | UX 设计选择：池展示需要一眼看 Top3，ATR 阈值在 alert-text 输出单独处理。不是 bug |
| **5** | `build_signal()` / `build_watch_alert()` / `generate_alert()` 语义冲突 | ✅ 部分已修 | commit `a27c338` — 180(真 bug: trigger text 取 alerts_found[0]) 已修复。3 个函数本来就是不同消费者：build_signal = 策略意图(JSON)，build_watch_alert = 执行卡，generate_alert = 单次推送文本。差异是**分层**，不是混乱 |

### P1 级：设计口径问题（不修代码，改文档）

以下项目**不改代码**，原因见表格最后一列：

| # | 问题 | 判断 | 原因 |
|---|------|------|------|
| **6** | `status`/`scene`/`signal_type`/`admission_result` 混用 | ❌ 不修 | `scene`(单票结构态) / `status`(池运维态) / `signal_type`(信号类型) 是**刻意分层**的三个层面。统一反而制造混乱 |
| **7** | `signals.jsonl` / `signal_log.jsonl` / `signal_results.jsonl` 职责不清 | ⚠️ 先统一主键再合并 | 先建稳定主键（含 signal_id + version + price），再迁移文件。**不能先合文件再想主键** |
| **8** | 三模块对支撑/压力/确认定义不一致 | ❌ 不修 | 单票 = 当日真值，池 = 入池快照(±1天)，复盘 = 验证态。**时间视角不同**，不是 bug |

### P2 级：验证器与测试

| # | 问题 | 状态 | 备注 |
|---|------|------|------|
| **9** | `validate_output.py` 与真实输出模板不同步 | ❌ 不适用 | validator 校验的是 contract layer（`schema/v1.py`），不是文本模板。已验证 OK |
| **10** | `self_check.py` 样本过时 | ✅ 已修 | commit `a27c338` 前后共 6 次修改 — 覆盖两场景、emoji/section 校正 |

### P3 级：架构边界（需讨论后决定）

| # | 问题 | 判断 |
|---|------|------|
| **11** | 缺少统一信号生命周期模型 | ✅ 同意。这是"为什么对不上"的底层根因 |
| **12** | 共享 schema 过宽，不能覆盖各包真实语义 | ✅ 同意。一个 schema 压太多业务，终会失真 |
| **A-1** | signal_id 稳定性和唯一性 | 需纳入统一生命周期模型 |
| **A-2** | `pipeline_state.json` 缺 schema | 中等优先级，补校验即可 |
| **A-3** | 缺统一信号生命周期模型（主键） | ✅ **最高优先级架构问题**，后两步的前提 |

---

## 二、修复顺序

### 第 0 步（已完成）
修掉已确认的真 bug：pipeline.write() / signal_id / trigger text / fix backfill NameError / fill_by_target 同名误填

### 第 1 步（待决定）
先统一主键模型（A-3），再合并三套 JSONL 文件

### 第 2 步（待决定）
统一信号生命周期设计文档

### 第 3 步（低优先级）
schema 分层讨论

---

## 三、验证方法

### 单点验证
- `pipeline_state.json` 是否只包含预期字段（stocks / market / positions）
- `stable_id()` 不同 price 产生不同 ID
- `fill_by_target()` 加 `signal_type` 后不再同名误填

### 链路验证
同一信号能否贯通：`build_signal()` → `append_signal()` → `load_recent_signals()` → `backfill()` → 池验证

### 跨模块验证
同一票在单票分析 / 选股池 / 盘后复盘 / 信号追踪 中的结论是否"可解释一致"

---

## 四、给另一个 AI 的决策提纲

可直接发给另一个 AI：

> Trader 项目当前状态：
> - P0 真 bug 已修 0/1（pipeline.write / signal_id / current_pct / trigger text 都已修复，cmd_watch 2% 是设计选择）
> - P1 中 6(status/scene) 和 8(支撑压力) 是刻意分层/时间视角差异，不改代码
> - P1 中 7(三套 JSONL) 需要先统一主键模型（A-3）再合并
   
> 下一步讨论：
> 1. signal_id 应该升级成什么粒度，才能贯穿生成、存储、追踪、回填、池验证？
> 2. 先合并 signals.jsonl / signal_log.jsonl / signal_results.jsonl，还是先定义统一生命周期再动文件？
> 3. pipeline_state.json 继续弱状态缓存，还是补 schema 校验？
