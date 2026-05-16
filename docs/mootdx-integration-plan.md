# mootdx 行情源集成规划

## 目标

在现有 `light_data.py` 中集成 **mootdx TCP 7709** 作为行情数据主源，降低 HTTP 封 IP 风险，增加逐笔成交等新能力。

## 字段映射

### K线 (BarData)

| BarData 字段 | 当前来源 | mootdx 字段 | 说明 |
|---|---|---|---|
| `date` | 腾讯 `row[0]` | `datetime` (int) | mootdx 返回时间戳，需 `str(datetime)` 转 YYYY-MM-DD |
| `open` | 腾讯 `row[1]` | `open` | 直接映射 |
| `close` | 腾讯 `row[2]` | `close` | 直接映射 |
| `high` | 腾讯 `row[3]` | `high` | 直接映射 |
| `low` | 腾讯 `row[4]` | `low` | 直接映射 |
| `volume` | 腾讯 `row[5]` | `vol` | 字段名不同，需 mapped |
| `amount` | ❌ 无 | `amount` | **新增字段** |

> 注：`tr / atr14 / atr7 / atr_ratio` 是由 `_compute_atr_fields()` 事后计算的，与数据源无关。

### 实时行情 (QuoteData)

| QuoteData 字段 | 当前来源 | mootdx 字段 |
|---|---|---|
| `current_price` | 腾讯报价 `fields[3]` | `price` |
| `pre_close` | 腾讯报价 `fields[4]` | `last_close` |
| `open` | 腾讯报价 `fields[5]` | `open` |
| `high` | 腾讯报价 `fields[33]` | `high` |
| `low` | 腾讯报价 `fields[34]` | `low` |
| `volume` | 腾讯报价 `fields[36]` | `vol` |
| `amount` | 腾讯报价 `fields[37]` | `amount` |
| `turnover_rate` | 腾讯报价 `fields[38]` | ❌ mootdx不含 → 仍用腾讯 |
| `current_change_pct` | 腾讯报价 `fields[32]` | 不含 → 需 `(price-last_close)/last_close` |
| PE/PB/市值 | 腾讯报价 `fields[39/46]` | ❌ mootdx不含 → 仍用腾讯 |

## 改造方案

### 架构: mootdx 主，腾讯备

```
fetch_qfq_daily():
  1. 尝试 mootdx bars()
  2. 失败时回退腾讯
  3. 统一走 _compute_atr_fields()

fetch_quote():
  1. 尝试 mootdx quotes()
  2. + 腾讯 PE/PB/市值 (通过已有接口)
  3. 合并返回
```

### 改动范围

**文件:** `02-共享模块-shared/01-行情数据-market-data/light_data.py`

| 改动 | 行范围 | 说明 |
|------|-------|------|
| 新增 import mootdx | 文件头 | `from mootdx.quotes import Quotes` |
| 新增 `_mootdx_client` 缓存 | ～L44 | 全局缓存，避免重复创建 |
| 新增 `_fetch_quote_mootdx(sec)` | ～L219 | 用 mootdx 拉 quote |
| 新增 `_fetch_qfq_mootdx(sec, days)` | ～L291 | 用 mootdx 拉 K线 |
| `fetch_qfq_daily()` 改为主 mootdx + 备腾讯 | L291-328 | 双源降级 |
| `fetch_quote()` 改为 mootdx + PE/PB 腾讯 | L219-252 | 双源合并 |
| `fetch_5m()` 可选 mootdx | L331-332 | mootdx 支持5分钟K线 |

### 不涉及改动

- `models.py` — 无需修改，字段一致
- `_compute_atr_fields()` — 数据源无关
- `fetch_kline()` / `fetch_15m()` / `fetch_30m()` — 先不动
- `MarketSnapshot` — 无需修改
- 功能包代码 — 无需修改

### 新增依赖

```bash
pip install mootdx
```

### 回退策略

腾讯行情源保留为 fallback，mootdx 不可用时自动降级，不阻断现有功能。

### 逐笔成交（后续扩展）

mootdx `transaction()` 提供逐笔成交数据，可后续在 `MarketSnapshot` 中扩展。

## 风险 & 注意事项

1. **海外环境 mootdx 超时** — mootdx 走 TCP 7709 直连通达信服务器，需要国内 IP 才稳定
2. **盘口字段 (bid/ask)** — 当前系统不直接消费，先不暴露
3. **mootdx 不含 PE/PB** — 腾讯仍需保留，只停掉腾讯 K线源
