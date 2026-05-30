## 1. T0 输出精简

- [x] 1.1 读取 T0 渲染脚本，理解当前 8 部分结构
- [x] 1.2 合并扫描结果+关键价位为「扫描」部分
- [x] 1.3 合并盘口验证+大单确认+今日事件为「盘中动态」部分
- [x] 1.4 合并仓位管控+下一步为「下一步」部分
- [x] 1.5 验证 T0 输出格式符合规范

## 2. review 命令结构配置

- [x] 2.1 编写 review/SKILL.md（职责说明+命令映射+输出格式）
- [x] 2.2 编写 review/hermes.yaml（触发词映射）
- [x] 2.3 编写 review/references/commands.md

## 3. run_trader.py 路由适配

- [x] 3.1 更新 run_trader.py 中的路径引用指向新目录（trader/t0/review）
- [x] 3.2 验证所有命令路由正常工作
