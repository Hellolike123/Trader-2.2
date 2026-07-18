# 代码审查提示词 — 2026-07-11 算法改进全面审查

## 背景

本项目是 A 股交易决策辅助系统（Trader 3.0）。2026-07-11 上午对缠论（Chanlun）和威科夫（Wyckoff）两个核心分析模块进行了大规模算法改进，共 20 项改动、14 个 commit。

**需要你做的事情**：对以下所有改动进行专业审查，找出 bug、逻辑漏洞、边界情况、潜在回归风险。

---

## 改动清单

### 一、缠论模块改进（`02-共享模块-shared/trader_shared/chan_core.py`）

#### P0: 分型双侧验证（commit d8547fa）
- **文件**: `chan_core.py:197-204` → `find_fractions()`
- **改动**: 顶分型从只检查 high 改为 high+low 都高于左右；底分型同理。删掉了十字星分支。
- **审查要点**: 双侧验证是否过严？是否会导致有效分型被过滤？与 czsc 的 `check_fx()` 实现是否一致？

#### P1: 笔端点极端值搜索（commit aac78ad）
- **文件**: `chan_core.py:386-430` → `build_strokes()`
- **改动**: 内层扫描从「遇到第一个合格反向就成笔」改为「在转折点范围内扫描所有合格反向，选最极端的成笔」。
- **审查要点**: 转折点（同向不更极端的分型）的 break 逻辑是否正确？极端值搜索是否会导致笔端点延迟确认？方向冲突处理是否正确？

#### P3: 包含处理修复（commit c438cc6）
- **文件**: `chan_core.py:161-193` → `handle_inclusion()`
- **改动**: 合并后重算 open/close（根据涨跌）、累加 vol/amount。
- **审查要点**: open/close 重算逻辑是否正确（涨→close=high, open=low）？vol/amount 累加是否会影响下游分析？与 czsc 的 `remove_include()` 是否一致？

#### P4: 笔力度三维度（commit c438cc6）
- **文件**: `chan_core.py:378-395` → `build_strokes()` 返回值
- **改动**: 新增 power_price、length 字段；传入 bars 时额外计算 power_volume。
- **审查要点**: power_volume 的计算范围（start_index+1 到 end_index-1）是否正确？边界条件处理？

#### P5: 背驰多维化（commit c438cc6）
- **文件**: `chan_core.py:965-1010` → `_stroke_force_weaker_multi()`
- **改动**: 新增三维力度衰减判定（MACD面积+价格力度+持续时间），至少 2 个维度衰减才判定为更弱。
- **审查要点**: 三维投票逻辑是否合理？单维度但 MACD 明确衰减时的回退是否正确？与原有 `_stroke_force_weaker` 的兼容性？

#### P6: 线段方向判定（commit c02d360）
- **文件**: `chan_core.py:453-466` → `build_segments()`
- **改动**: 第 3 笔未确认方向时，用首尾笔端点推断方向。
- **审查要点**: 推断逻辑（third_end > first_end → up）是否符合缠论标准？与原来的 fallback 相比是改进还是退步？

#### P7: 一类买卖点 fallback 加强（commit c02d360）
- **文件**: `chan_core.py:1232-1249` → `detect_buy_points()` 一类买 fallback
- **改动**: 从 2 根柱状线回升改为 3 根连续回升；无 bars 时兼容旧逻辑。
- **审查要点**: 3 根连续回升是否太严格？兼容旧逻辑的 fallback 是否正确？

#### P8: 二类买卖点条件修复（commit c02d360）
- **文件**: `chan_core.py:1275-1288` → `detect_buy_points()` 二类买
- **改动**: 两笔之间无同向笔时跳过（不再用全局极值做宽松条件）。
- **审查要点**: 这个改动是否会导致有效二类买信号被漏掉？

#### 其他
- `CHANLUN_MIN_BARS_PER_STROKE` 从 5 改为 6（commit d1bfaee）
- 三类买卖点 freshness 从 2 笔放宽到 3 笔（commit d1bfaee）

---

### 二、威科夫模块改进（`02-共享模块-shared/trader_shared/wyckoff_core.py`）

#### P1-1: Spring 一字板过滤（commit 361c500）
- **函数**: `_is_frozen_board(bar)` + `_detect_spring()` 入口检查
- **改动**: 检测开=高=低=收的冻结交易日，排除无效 Spring 测试。
- **审查要点**: 1% 阈值是否合适？是否会导致正常小波动被误判为一字板？

#### P1-2: 涨跌停板量能缩放（commit 361c500）
- **函数**: `_board_vol_scale(symbol)` + `_detect_spring()` 量能分级
- **改动**: 创业板/科创板量能阈值放大 1.41x。
- **审查要点**: 1.41x（sqrt(20/10)）是否合理？是否需要区分不同板块？

#### P1-3: 交易区间检查（commit 361c500）
- **函数**: `_is_trading_range(bars)` + `_detect_spring()` 入口检查
- **改动**: 计算 ATR 和整体振幅，要求振幅不超过 max(ATR% × 4, 30%)。
- **审查要点**: 4x ATR 的阈值是否合理？30% 的最低保底是否合适？

#### P2: Compression 压缩蓄势（commit 886efda）
- **函数**: `_detect_compression(bars)`
- **改动**: 检测 ATR 分位<20% + 量能枯竭 + 非下降结构。
- **审查要点**: ATR 分位计算是否正确？量能萎缩阈值 0.6 是否合理？非下降结构检查逻辑？

#### P3: Trend Pullback 趋势回踩（commit 886efda）
- **函数**: `_detect_trend_pullback(bars)`
- **改动**: 检测回撤 5-20% + 缩量 + 站稳 MA20 + MA 上升。
- **审查要点**: MA20 的计算方式？回撤幅度范围是否合理？缩量阈值？

#### 集成改动
- `wyckoff_analysis()` 新增 symbol 参数，贯穿全链路
- `_detect_phase()` 新增 compression/trend_pullback 阶段分类
- `calculate_wyckoff_score()` 新增 compression(+10)/trend_pullback(+8) 权重
- `format_wyckoff_oneline()` 优先链新增两个信号

---

### 三、代码质量优化

#### MACD 去重（commit 137e372）
- **文件**: `indicator_math.py` 新增 `calc_macd_series()`；`chan_core.py`、`structure_core.py`、`momentum_core.py` 改为调用统一函数
- **审查要点**: 三处调用是否都正确传参？`momentum_core.calc_macd` 的外部 API 是否保持不变？

#### swing-low 去重（commit ee58842）
- **文件**: `structure_core.py` 新增 `_find_swing_lows()` 公共函数
- **审查要点**: 三处调用是否都正确替换了？逻辑是否完全等价？

#### _load_confidence_params 缓存（commit ee58842）
- **文件**: `fusion_core.py` 新增模块级缓存
- **审查要点**: 缓存是否会导致 stale data 问题？self_calibration 更新后缓存是否失效？

---

### 四、测试覆盖

#### 新增测试文件
- `test_indicator_math.py` — 22 个用例（EXPMA/MACD 序列）
- `test_rule_engine.py` — 18 个用例（沙箱/规则引擎）
- `test_account_risk.py` — 13 个用例（账户风控）

#### 新增测试用例（已有文件）
- `test_chan_core.py` — 3 个 P4 笔力度测试
- `test_wyckoff_core.py` — 14 个 P1/P2/P3 测试

---

## 审查要求

### 1. Bug 检测
- 检查每个改动的边界条件（空输入、None、极端值）
- 检查是否有 off-by-one 错误
- 检查是否有未处理的异常情况

### 2. 逻辑正确性
- 每个算法改动是否符合缠论/威科夫的标准定义？
- 改动是否与上下游模块（fusion、discipline、report）正确集成？
- 向后兼容性是否保证？

### 3. 性能影响
- 新增的计算（如 power_volume、ATR 分位数）是否有性能问题？
- 缓存策略是否正确？

### 4. 测试覆盖
- 现有测试是否覆盖了新增功能的关键路径？
- 是否缺少重要的边界条件测试？

### 5. 代码质量
- 命名是否清晰？
- 是否有重复代码？
- 是否有死代码？

---

## 输出格式

请按以下格式输出审查结果：

```
## 审查报告

### 发现的问题

| # | 严重度 | 文件:行号 | 问题描述 | 建议修复 |
|---|--------|-----------|----------|----------|

### 改进建议

| # | 优先级 | 建议内容 |

### 总体评估

- 代码质量: X/10
- 算法正确性: X/10
- 测试覆盖: X/10
- 向后兼容性: X/10
```
