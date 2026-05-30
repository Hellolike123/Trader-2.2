## 1. 目录结构

- [ ] 1.1 创建 `01-功能包-packages/trader/` 新目录结构（scripts/、references/、tests/）
- [ ] 1.2 创建 `01-功能包-packages/t0/` 新目录结构
- [ ] 1.3 创建 `01-功能包-packages/review/` 新目录结构

## 2. trader skill（分析+选票）

- [ ] 2.1 合并 01-单票分析-trader 和 03-选股池-trader-pool 的脚本到 trader/
- [ ] 2.2 从 run_analysis.py 移除扩展数据（_enrich_snapshot 调用）
- [ ] 2.3 实现四阶段定位逻辑（大阶段判定 + 短期动能判定 + 组合决策矩阵）
- [ ] 2.4 修改 250日线一票否决为提醒不屏蔽
- [ ] 2.5 实现仓位跟着大阶段走（ATR 变成阶段内微调）
- [ ] 2.6 统一 trader 输出格式（trader 输出模板）
- [ ] 2.7 编写 trader 的 SKILL.md / commands.md / output-contract.md
- [ ] 2.8 编写 trader 的 _meta.json / HERMES.md

## 3. t0 skill（盘中盯盘）

- [ ] 3.1 迁移 02-盘中T0-t0-trader 脚本到 t0/
- [ ] 3.2 变薄 t0 职责（只看+只响，读 pool.json）
- [ ] 3.3 统一 t0 输出格式（t0 输出模板）
- [ ] 3.4 编写 t0 的 SKILL.md / commands.md / output-contract.md
- [ ] 3.5 编写 t0 的 _meta.json / HERMES.md

## 4. review skill（盘后复盘+仓位+追踪）

- [ ] 4.1 合并 04-仓位轮动 + 05-盘后复盘 + 06-信号追踪 到 review/
- [ ] 4.2 统一 review 输出格式（个股复盘模板）
- [ ] 4.3 实现仓位轮动输出格式
- [ ] 4.4 实现信号统计分析新格式（纯数字，不给建议）
- [ ] 4.5 编写 review 的 SKILL.md / commands.md / output-contract.md
- [ ] 4.6 编写 review 的 _meta.json / HERMES.md

## 5. 分析引擎优化

- [ ] 5.1 实现 chanlun/wyckoff/momentum 并行化（ThreadPoolExecutor）
- [ ] 5.2 验证并行化结果与串行一致

## 6. 打包与路由

- [ ] 6.1 重写 pack_all.py 支持 3 个新 skill 目录
- [ ] 6.2 更新 trader.py CLI 路由（analyze/monitor/pool/review/portfolio/track → 新目录）
- [ ] 6.3 更新 t0_cron.py 路径
- [ ] 6.4 更新 run_trader.py 路径

## 7. 清理

- [ ] 7.1 删除旧的 6 个 skill 目录
- [ ] 7.2 更新 AGENTS.md 反映新结构
- [ ] 7.3 运行全量测试 + pack_all 验证
- [ ] 7.4 验证所有命令正常工作
