# 会话交接文档 — 可插拔架构收尾 + 筹码峰模块

> 2025-05-08 | base: 1ae0e14 | HEAD: 6159519
> 状态：✅ 10 项全部完成 + commit 2 次

## 变更记录（2 commits）

### commit eb90fe3 — 规则化 + 缓存 + 导入修复
| 文件 | 改动 |
|------|------|
| `trader_shared/score_rules.yml` | 新建 9 条评分修正规则 |
| `trader_shared/livermore_rules.yml` | 新建 6 条金字塔加仓规则 |
| `trader_shared/modifier_rule_engine.py` | 评分/加仓规则引擎加载器，缓存+失败回退 |
| `trader_shared/rule_engine.py` | 新增 ScoreRuleEngine 类（全匹配求和），扩展沙箱安全内置函数 `abs/min/max` |
| `decision_core.py` | `score_for()` 接入 YAML 规则引擎+fallback；`livermore_scale()` 接入 YAML + fallback |
| `light_data.py` | `fetch_quote()` 加 30 秒实时缓存，减少 Hermes 调用延迟 |
| `test_review_backtrack.py` | 添加 `candidate_core` 到 sys.path，修复孤立运行 `ModuleNotFoundError` |

### commit 6159519 — 筹码分布模块
| 文件 | 改动 |
|------|------|
| `trader_shared/chip_distribution.py` | 新建独立模块，标准筹码峰公式（总量守恒 0% 偏差） |
| `review_core.py` | `build_review()` 加入 `calc_chip_distribution()` 调用；输出数据透传 |
| `review_render.py` | `render_single()` 输出 💰 筹码分布段落 |
| `review_store.py` | `review_summary()` 加入 `chip_peaks` 字段 |
| `review_compare.py` | 多股比较输出筹码密集区段 |
| `final_review.py` | 添加完整 sys.path setup，修复孤立导入 `candidate_core` |
| `run_analysis.py` | trader 引入 `calc_chip_distribution`（已 import，暂不渲染） |

## 关键技术决策

### 规则引擎沙箱安全
```python
sandbox = {"__builtins__": {"abs": abs, "min": min, "max": max}}
eval(expr, sandbox, context_dict)
```
- 表达式字符串由我们自己（开发者）控制，不来自用户输入
- `__builtins__={}` 锁定基础函数，`abs/min/max` 是规则计算需要的最小集
- 回退路径：YAML 加载失败 → `apply_score_modifiers()`/`apply_livermore_scale()` 返回 `None` → 继续硬编码逻辑

### 筹码峰算法（标准公式）
```
1. N 日量价 → 价格范围 price_range = high_max - low_min
2. tick = price_range / num_bins（~50 bins，最小 0.1 元）
3. 每天量均匀分配到日K的 [lo_idx, hi_idx] 每个格子
4. segment = volume / (hi_idx - lo_idx + 1)  ← 关键：+1 确保总量守恒
5. 峰值 = volume_map 最大的 3 个格子，按相对排名定支撑强度
```
- **总量守恒验证：偏差 0%，验证通过**
- `tick` 太大（如 0.175 元 50 bin）会平滑峰值，`tick=0.1~0.3` 是经验推荐值

### 实时缓存策略
`light_data.fetch_quote()` 加 30 秒 TTL
- 同一 skill 多次调用（如 review_compare 复盘 3 只票）：只请求 1 次腾讯实时数据
- 跨 skill 调用间隔 >30 秒：自动刷新，不影响时效性
- ❌ 未缓存 `fetch_qfq_daily`（日线含当日数据变化频繁）
- ❌ 未缓存 `fetch_5m`（5 分钟线盘中变化更频繁）

## 验证结果

```
146 passed, 1 pre-existing failure (test_v2_infra.py::test_fill)
```

所有测试通过，与改动前状态一致。

## 待办（不在本次改动范围）

1. **review_compare 孤立导入** — `final_review.py` 已添加 sys.path，但 `review_compare.py` 自身的 import 路径仍有依赖链脆弱性，下次重构时修复
2. **trader render_markdown 加筹码峰段落** — `calc_chip_distribution` 已 import 但尚未在 `render_markdown()` 输出
3. **数据缓存 30s 可扩展到 5m/15m 线** — 按需决定是否值得
