## Why

T0 输出有 8 个部分（重叠严重），需要精简为 4 部分。review 命令结构需要配置 SKILL.md 和 hermes.yaml。run_trader.py 路由需要适配新的 3-skill 结构。

## What Changes

- T0 输出精简为 4 部分：扫描、盘中动态、下一步（合并扫描结果+关键价位+盘口+大单+事件+仓位+下一步）
- review 命令结构配置（SKILL.md / hermes.yaml / commands.md）
- run_trader.py 路由适配新 3-skill 目录（trader/t0/review）

## Impact

- 修改文件：t0/scripts/ 下的渲染脚本、review/ 的 SKILL.md/hermes.yaml、scripts/run_trader.py
