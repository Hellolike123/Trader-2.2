## Context

T0 输出当前有 8 个部分，内容重叠严重。review 已合并三个功能但命令结构未配置。run_trader.py 还指向旧目录。

## Goals / Non-Goals

**Goals:**
- T0 输出精简为 4 部分
- review 命令结构配置
- run_trader.py 路由适配

**Non-Goals:**
- 不改变 T0 核心监控逻辑
- 不改变 review 复盘计算逻辑

## Decisions

### 1. T0 输出精简

原来 8 部分 → 4 部分：
- 扫描（合并扫描结果+关键价位）
- 盘中动态（合并盘口验证+大单确认+今日事件）
- 下一步（合并仓位管控+下一步）

告警卡和熔断告警保持不变。

### 2. review 命令结构

Hermes 自然语言触发，不需要记命令。配置 hermes.yaml 映射触发词。

### 3. run_trader.py 路由

更新路径指向新目录：trader/t0/review。
