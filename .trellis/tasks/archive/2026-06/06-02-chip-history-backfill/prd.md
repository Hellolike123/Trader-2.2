# 筹码历史数据回填

## Goal

抓取前两周的筹码分布数据，让"筹码变化（对比昨天）"功能立即可用。

## 问题

目前 `chip_history.json` 只有今天的数据，无法显示筹码变化。需要回填历史数据。

## 实现方案

### 方案 A：运行时回填（推荐）

在 `chip_migration_monitor.py` 中添加回填逻辑：
1. 检查 `chip_history.json` 是否有昨天的数据
2. 如果没有，自动抓取前两周 K 线数据
3. 计算每天的筹码分布
4. 保存到 `chip_history.json`
5. 只回填一次（有历史数据就不回填）

### 方案 B：独立脚本

创建 `scripts/backfill_chip_history.py`：
1. 手动运行
2. 抓取指定股票前两周数据
3. 计算并保存筹码分布

## 数据结构

```json
{
  "南网科技": {
    "date": "2026-06-02",
    "peaks": [...],
    "current_pct": 67.3,
    "mid_price": 60.29
  },
  "南网科技_2026-06-01": {
    "date": "2026-06-01",
    "peaks": [...],
    "current_pct": 65.0,
    "mid_price": 59.80
  }
}
```

## 实现步骤

1. 修改 `chip_migration_monitor.py` 添加 `backfill_history()` 函数
2. 在 `check_chip_migration()` 中调用回填逻辑
3. 回填时计算每天的筹码分布并保存
4. 对比时使用昨天的数据

## 验收标准

- [ ] 运行 `trader script --target 南网科技` 显示筹码变化
- [ ] 筹码变化显示"对比昨天"的数据
- [ ] 回填只执行一次（有历史数据就不回填）
- [ ] 测试通过
