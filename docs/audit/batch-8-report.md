# 第 8 批审查报告 — data_status=partial 根因排查与修复

> 触发：用户发现单票分析 `data_status` 常被标记为 `partial`，最初误判为"东方财富资金流连接失败"。
> 流程：实跑 688248 提取 `missing_sources`/`source_errors` → 逐层定位 → 修复 → 端到端验证。

## 一、现象与错误归因纠正

实跑 `trader.py analyze --target 688248 --output json`：

```
修复前: data_status = "partial"  missing_sources = ["weekly_bars","monthly_bars"]  source_errors = {}
```

**纠正**：`source_errors = {}` 说明资金流本次并未失败。`partial` 的真正驱动是 `missing_sources`（周月线缺失），与资金流是两个独立现象。

## 二、根因链（三层，逐步定位带行号）

```
data_status=partial
 └─ missing_sources=["weekly_bars","monthly_bars"]        ← 第一层根因
      └─ fetch_weekly/fetch_monthly 返回 []                （light_data.py:1344/1355 → _fetch_mins_mootdx）
           └─ _get_mootdx_client() 返回 None                （light_data.py:584）
                └─ _check_mootdx() 返回 False               ★第二层根因
 └─ 修复第二层后 weekly/monthly 取到，但 daily_bars 含 1 条质量 partial bar
      └─ load_market_snapshot 判定检查各源 internal bar 的 data_status=="partial"
         （light_data.py:1555）→ 即使所有源都取到，整体仍 partial   ★第三层根因
```

### 根因 1（第二层）：`_check_mootdx` 导入名错误
`light_data.py:47` 原代码：
```python
from mootdx.quotes import Q      # ← 导出名错误，实际为 Quotes
Quotes = Q
```
mootdx 实际导出 `Quotes`（与 L590 `Quotes.factory` 一致），`from ... import Q` 永远抛 `ImportError` → `_MOOTDX_AVAILABLE=False` → mootdx 整条备份通道（周月线/分钟线 fallback/日线 fallback/quote fallback）**全部失效**。系统只靠腾讯/新浪 HTTP 跑，周月线（代码写死只走 mootdx，Sina 不支持）永远拿不到。

实测（修复前）：`_check_mootdx()=False`、`_get_mootdx_client()=None`、`weekly=None`。

### 根因 2：fetch_weekly/fetch_monthly 误标 partial
`light_data.py:1348/1359` 无条件把取到的周月线 bar 标 `data_status="partial"`。但 mootdx 是周月线**唯一主源**（Sina 不支持），取到即完整数据，不应标 partial。这导致上层判定把它们当降级源。

### 根因 3（第三层，终极元凶）：data_status 判定被内部个别 bar 反向降级
`light_data.py:1552-1558` 原逻辑检查**各源 internal bar** 的 `data_status=="partial"`。而 `fetch_qfq_daily` 总有个别 bar 因非前复权等细节标 `partial`（实测 `daily_bars TOTAL=502 data_status=Counter({'full':501,'partial':1})`），命中 `any(...=="partial")` → 整体永远 `partial`。

这是"即使所有源都取到数据，整体也 partial"的真正原因——只要是日线就总有质量 partial bar。

## 三、修复（light_data.py，3 处）

1. **L47-48** `_check_mootdx` 导入名修正：
   ```python
   from mootdx.quotes import Quotes
   _MOOTDX_AVAILABLE = True
   except ImportError:
       Quotes = None
       _MOOTDX_AVAILABLE = False
   ```
2. **L1348 / L1359** `fetch_weekly`/`fetch_monthly` 标 `"full"`（mootdx 周月线成功即完整，与 fetch_kline 的 sina 成功分支一致）。
3. **L1552-1561** `load_market_snapshot` data_status 判定改为只由 `missing_sources`（分项源是否整体缺失）+ 核心 `quote` 是否降级决定；各源 internal bar 的质量标记（非前复权/fallback）已在字段暴露给下游，不再反向降级整体完备度。

## 四、验证

| 验证项 | 结果 |
|--------|------|
| 实跑 probe `load_market_snapshot("688248")` | `data_status=full`，`missing_sources=[]`，各源全 `full` |
| 端到端 `trader.py analyze 688248` | `data_status=full`，现价/支撑阻力/ma250/融合动作/周月线收盘价均正常 |
| 端到端 `trader.py analyze 600519`（另一只） | `data_status=full`，通用性确认 |
| 回归 `test_light_data_mootdx / test_data_provider / test_qfq_fallback / test_fusion_integration / test_indicator_enhancements` | **42 passed** |
| 新增 `test_data_status_decision.py`（mock 源，不依赖网络） | **3 passed**（daily 含 partial→full；weekly 缺失→partial；happy path→full） |

## 五、结论

`data_status=partial` 不是"正常现象"，而是 **3 层真实 bug** 叠加导致：
- mootdx 备份通道因导入名错误整体失效（影响周月线 + 所有 fallback）；
- 周月线取到后仍被误标 partial；
- 日线个别质量 partial bar 被上层误判为整体降级。

修复后数据完备度语义正确：所有源齐全 → `full`；某分项源缺失 → `partial`（仍保守）；核心 quote 降级 → `partial`。融合层 `fusion_core` 的保守动作逻辑（partial 时压低 action）仍只在真缺失时触发，行为更准。

本次修复未破坏任何既有分析与测试。报告与代码已合并 main（默认不 push）。
