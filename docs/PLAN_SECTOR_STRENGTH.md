# 板块相对强度 — 实现方案

## 目标

在融合层中增加第四路信号：个股所属行业的整体表现，计算"个股涨跌幅 vs 板块中位数涨跌幅"的差值，作为相对强度因子参与决策加权。

优先级：P2（P0 止损升级已完成）

---

## 数据源

### 源 1：行业板块排行 API

```
东财 API (无需 token，纯 JSON)
GET https://push2.eastmoney.com/api/qt/clist/get
  ?pn=1&pz=60           ← 前 60 个行业
  &fs=m:90+t:2           ← m:90=板块, t:2=行业板块
  &fields=f2,f3,f4,f12,f14
  # f2=最新价  f3=涨跌幅  f4=涨跌额
  # f12=板块代码(如 BK0895)  f14=板块名称
```

返回示例：
```json
{
  "data": {
    "diff": [
      {"f12":"BK0895","f14":"计算机设备","f3":1.25,"f2":1420.5},
      {"f12":"BK0477","f14":"半导体","f3":-0.83,"f2":3210.8}
    ]
  }
}
```

**缓存在内存**，TTL=600s（10 分钟内不重复请求）。板块中位数涨跌幅非交易时段也不变。

### 源 2：个股所属行业名称

**不需要额外 HTTP 请求。** 腾讯实时行情 `qt.gtimg.cn` 返回的 `fields[39]` 或 `fields[40]` 包含个股所属行业名称。`light_data.py` 的 `fetch_quote()` 已经在解析腾讯字段，只需新增字段提取。

`light_data.py` `fetch_quote()` 中 Tencent HTTP 分支增加：
```python
"industry": fields[39] if len(fields) > 39 else None,
```

这样 `quote["industry"]` 就有值了。然后用行业名称去匹配源 1 的板块排行。

---

## 新增文件：`sector_strength.py`

位置：`02-共享模块-shared/trader_shared/sector_strength.py`

```python
"""
板块相对强度计算。

流程：
  1. fetch_sector_ranking() → 拉东财行业板块排行，缓存 600s
  2. get_sector_change(industry_name) → 根据行业名查板块涨跌幅
  3. relative_strength(stock_change_pct, sector_change_pct) → 计算相对强度
"""

import time
import sys
from typing import Any

_SECTOR_CACHE: dict[str, Any] = {"data": None, "ts": 0.0}
_SECTOR_TTL = 600  # 10 秒


def fetch_sector_ranking() -> dict[str, float] | None:
    """拉取东方财富行业板块涨跌幅排行，返回 {板块名: 涨跌幅} 映射。"""
    now = time.time()
    if _SECTOR_CACHE["data"] is not None and now - _SECTOR_CACHE["ts"] < _SECTOR_TTL:
        return _SECTOR_CACHE["data"]

    try:
        from trader_shared.extend_data import _http_get_json

        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": 1, "pz": 60,
            "fs": "m:90+t:2",
            "fields": "f2,f3,f4,f12,f14",
        }
        resp = _http_get_json(url, params)
        items = resp.get("data", {}).get("diff", [])
        if not items:
            return None

        result: dict[str, float] = {}
        for item in items:
            name = str(item.get("f14", "")).strip()
            chg_pct = item.get("f3")
            if name and chg_pct is not None:
                result[name] = float(chg_pct)

        _SECTOR_CACHE["data"] = result
        _SECTOR_CACHE["ts"] = now
        return result

    except Exception:
        return None


def get_sector_change(industry_name: str) -> float | None:
    """根据行业名称获取板块涨跌幅。

    用子串匹配（如"计算机设备"可匹配"计算机设备、IT 服务"等变体）。
    """
    ranking = fetch_sector_ranking()
    if not ranking or not industry_name:
        return None

    # 精确匹配优先
    if industry_name in ranking:
        return ranking[industry_name]

    # 子串匹配：行业名含于板块名，或板块名含于行业名
    for sector_name, chg in ranking.items():
        if industry_name in sector_name or sector_name in industry_name:
            return chg

    return None


def relative_strength(
    stock_change_pct: float | None,
    sector_change_pct: float | None,
) -> float | None:
    """计算个股相对板块的超额收益。

    正值 = 个股跑赢板块，负值 = 个股跑输板块。
    """
    if stock_change_pct is None or sector_change_pct is None:
        return None
    return stock_change_pct - sector_change_pct
```

---

## 数据链路改动

### 1. `light_data.py` — 行情增加行业字段

`fetch_quote()` 中 Tencent HTTP 分支（约第 738 行）：

```python
# 在现有的字段解析块中增加
"industry": fields[39] if len(fields) > 39 else None,
```

mootdx 和 pytdx3 的 quote dict 不需要改（它们不返回行业信息，Tencent HTTP 是第一优先，成功返回后不会再走 mootdx 路径）。

### 2. `market_env.py` — 扩展 `assess()` 返回板块强度

在 `assess()` 返回的 dict 中增加 `sector_*` 字段：

```python
try:
    from trader_shared.sector_strength import sector_change_for
    sec = resolve_security(INDEX_CODE)
    quote = fetch_quote(sec, HttpClient())
    industry = quote.get("industry") if quote else None
    sector_chg = sector_change_for(industry) if industry else None
    result["sector_change"] = sector_chg
    result["sector_name"] = industry
except Exception:
    pass
```

### 3. `fusion_core.py` — 第四路信号入融合层

`merge_decisions()` 增加 `sector_rel_strength: float | None` 参数（约第 205 行）：

```python
def merge_decisions(
    chan_result: dict,
    momentum_result: dict,
    wyckoff_result: dict,
    regime: str,
    current_price: float,
    bars: list,
    hmm_regime: str = "range",
    extend_fundamental: dict | None = None,
    extend_sentiment: dict | None = None,
    sector_rel_strength: float | None = None,  # ← 新增
) -> dict:
```

在信号标准化阶段增加第四路信号（约第 210 行）：

```python
# 板块相对强度信号
_sector_signal = {"direction": 0, "confidence": 0.3, "reason": ""}
if sector_rel_strength is not None:
    # 跑赢板块 2% 以上 = 看多，跑输 2% 以上 = 看空
    if sector_rel_strength > 2.0:
        _sector_signal["direction"] = 1
        _sector_signal["confidence"] = min(0.6, abs(sector_rel_strength) / 10)
        _sector_signal["reason"] = f"跑赢板块 {sector_rel_strength:+.1f}%"
    elif sector_rel_strength < -2.0:
        _sector_signal["direction"] = -1
        _sector_signal["confidence"] = min(0.6, abs(sector_rel_strength) / 10)
        _sector_signal["reason"] = f"跑输板块 {sector_rel_strength:+.1f}%"
    else:
        _sector_signal["direction"] = 0  # 与板块同步，中性
        _sector_signal["confidence"] = 0.2
        _sector_signal["reason"] = "与板块同步"
```

在 Scenario Priority Filter 权重分配中增加板快权重（约第 260 行）：

```python
# 极端行情时板块因子权重提高
if regime == "很差":
    sector_weight = 0.15
    # 从其他因子等比扣除
    scale = 1 - sector_weight
    ...
```

signals_detail 和 weights_used 的输出中也增加 `"sector"` 键。

### 4. `run_analysis.py` — 传板块参数

`build_report()` 中调用 `merge_decisions()` 时传入：

```python
# 计算板块相对强度
try:
    from trader_shared.sector_strength import get_sector_change, relative_strength
    industry = quote.get("industry")
    sector_chg = get_sector_change(industry) if industry else None
    stock_chg = quote.get("current_change_pct")
    sector_rel = relative_strength(stock_chg, sector_chg)
except Exception:
    sector_rel = None

report_fusion = merge_decisions(
    ...,
    sector_rel_strength=sector_rel,  # ← 传入
)
```

---

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `trader_shared/sector_strength.py` | **新建** | 板块排行拉取 + 相对强度计算 |
| `light_data.py` | 改 1 行 | Tencent HTTP 分支增加 `industry` 字段 |
| `fusion_core.py` | 改 ~20 行 | 新增 `sector_rel_strength` 参数 + 信号标准化 + 权重调整 |
| `run_analysis.py` | 改 ~8 行 | `build_report()` 中计算 `sector_rel` 传入融合层 |
| `config.py` | 改 0 行（可选） | 如需开关控制可加 `ENABLE_SECTOR_STRENGTH = True` |

---

## 改动量估算

| 文件 | 新增行 | 修改行 |
|------|--------|--------|
| `sector_strength.py` | ~70 | 0 |
| `light_data.py` | 1 | 0 |
| `fusion_core.py` | ~20 | ~5 |
| `run_analysis.py` | ~8 | ~1 |
| 合计 | ~99 | ~6 |

纯 Python，零新依赖（复用已有 `_http_get_json`），正向兼容（`sector_rel_strength=None` 时融合层行为不变）。

---

## 输出效果

决策分解日志会多一行：

```
  板块：计算机设备 涨 +1.25%（个股 +3.50%，跑赢 +2.25% → 看多，置信 45%）
```
