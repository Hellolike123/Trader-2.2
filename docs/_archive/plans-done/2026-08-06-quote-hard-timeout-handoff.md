# 腾讯 quote 硬超时（d）handoff

> 状态：active（2026-08-06）
> 触发：单票 snapshot 慢（Agent 高频命令 final_report --target）
> 法源：`light_data.fetch_quote` · `_run_with_hard_timeout` · `run_tdx3_with_timeout(2.0s)` · `run_mootdx_with_timeout(2.5s)`

## 一、实测证据

- 探针（单进程串行计时）：**quote 冷取 4.40s**（唯一慢腿；daily 缓存 0s、5m 1.23s、weekly 0.97s）
- 腾讯端点 4 轮直测：0.42/0.30/0.16/0.17s 全 valid → **偶发慢响应/失败**，非系统性慢
- `fetch_quote` 腾讯分支：`http.get_text(..., max_retries=2)` + 全局 `TIMEOUT_SECONDS=5` → **最坏 3×5s+退避 ≈ 15.7s** 才 fallback
- 对比：tdx3 已用硬超时 2.0s、mootdx 2.5s；腾讯无硬超时

## 二、方案

腾讯 quote 调用包 `_run_with_hard_timeout(timeout_s=2.5)` + `max_retries=0`：

- 保持腾讯优先（快时 0.2~0.4s 赢）
- 偶发慢/超时 → 2.5s 硬切 pytdx3/mootdx（实测 0.58s）
- 熔断器在首次失败后打开 → 后续同进程直接 mootdx（成本只付一次）
- 与 tdx3/mootdx 超时模式一致

## 三、必须（验收表）

| # | 必须项 | 验收 |
|---|--------|------|
| 1 | 腾讯快时仍腾讯赢（data_source=tencent-http） | 正常网络下 fetch_quote source=tencent-http |
| 2 | 最坏腾讯等待 ≤ ~2.5s 边界 | 慢响应/超时模拟 quote ≤ ~3s |
| 3 | 腾讯失败 → pytdx3/mootdx 正常接管 | 断网/慢网模拟 source=mootdx |
| 4 | 不改变数据语义（字段/优先级/回退链） | diff 仅 fetch_quote 腾讯分支 |
| 5 | 门禁全绿 | run-gate-tests.sh |

## 四、禁止

- 禁止改 `TIMEOUT_SECONDS`（全局，影响 5m/日K/周线）
- 禁止改 tdx3/mootdx 超时（已合理）
- 禁止换源优先级（腾讯仍第一优先）

## 五、可改文件白名单

- `02-共享模块-shared/trader_shared/light_data.py`（仅 fetch_quote 腾讯分支 + 常量）
- 本 handoff

## 六、执行顺序

1. 加常量 `TENCENT_QUOTE_HARD_TIMEOUT_S = 2.5`；腾讯调用包 `_run_with_hard_timeout(..., 2.5)` + `max_retries=0`
2. 验证 #1（正常网络 source=tencent-http）+ #3（断网 source=mootdx）
3. 门禁（#5）
4. 本 handoff 归档

## 七、执行结果（2026-08-06）

- **实现**：常量 `TENCENT_QUOTE_HARD_TIMEOUT_S=2.5` + 腾讯分支包 `_run_with_hard_timeout(..., 2.5)` + `max_retries=0`
- **实测修正认知**：本机 `detect_trader_host()=workbuddy`（~/.workbuddy/connectors 存在）→ quote 主路径 = tdx3→**mootdx**（0.4~0.7s），腾讯分支仅兜底。改动主要服务 Hermes/local host（腾讯优先）与本机 mootdx 失败后的兜底腿
- **三场景验证**（清缓存重测）：
  - A 本机 WorkBuddy：mootdx 0.70s ✅
  - B Hermes 模式（tdx_first=False）+ 腾讯快：**tencent-http 赢 1.43s**（优先级未破坏）✅
  - C Hermes 模式 + 腾讯挂 6s：**2.55s 硬切 mootdx**（2.5s 上限生效）✅
- **最坏等待账**：腾讯腿 15.7s（3×5s 重试）→ **2.5s**；本机组合最坏 mootdx 2.5s + 腾讯 2.5s ≈ 5s（原 mootdx 2.5s + 腾讯 15.7s ≈ 18s）
- **门禁**：742 passed / 0 failed ✅
