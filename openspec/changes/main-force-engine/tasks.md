## 1. 数据采集模块

- [x] 1.1 新建 `trader_shared/fund_flow_data.py`，实现 `fetch_fund_flow(sec)` 函数，通过东方财富HTTP API获取近30日个股资金流向数据
- [x] 1.2 实现东方财富API的 secid 映射逻辑（沪市=1，深市=0，含创业板/科创板识别）
- [x] 1.3 实现 `calc_fund_flow_features(daily_flow, bars)` 函数，计算衍生特征：cum_flow_5d、cum_flow_10d、consecutive_inflow/outflow_days、net_flow_pct、flow_price_relation
- [x] 1.4 实现价资关系判断逻辑：比较近5日价格变动方向与资金流向方向，输出六种关系描述之一

## 2. 缓存集成

- [x] 2.1 在 `cache_utils.py` 中新增 `CACHE_FUND_FLOW = "fund_flow"` 常量和 `TTL_FUND_FLOW = 86400` 常量
- [x] 2.2 实现 `fetch_fund_flow_cached(sec)` 函数，读缓存→过期则调API→写缓存
- [x] 2.3 在 `warm_pool_cache()` 中增加资金流向预缓存步骤，遍历选股池活跃股票调用 `fetch_fund_flow_cached`
- [x] 2.4 验证 `trader.py cache clear --type fund_flow` 和全量清理均能正确清理 fund_flow 缓存（clear_cache 已支持子目录清理）

## 3. 主力行为识别引擎

- [x] 3.1 新建 `trader_shared/main_force.py`，实现 `detect_main_force_stage(features, bars, chip_info)` 主函数
- [x] 3.2 实现吸筹期检测规则：价格横盘 + 净流入 + 筹码集中
- [x] 3.3 实现试盘期检测规则：单日脉冲上涨 + 大额净流入 + 次日回落
- [x] 3.4 实现拉升期检测规则：连续净流入 + 量比放大 + 价格突破
- [x] 3.5 实现派发期检测规则：高位滞涨 + 净流出 + 筹码松散
- [x] 3.6 实现砸盘期检测规则：连续净流出 + 放量下跌
- [x] 3.7 实现置信度计算逻辑，根据条件满足程度给出 0.0-0.8 的置信度
- [x] 3.8 实现信号列表生成，输出触发阶段判断的具体条件描述

## 4. 融合层集成

- [x] 4.1 在 `fusion_core.py` 的 `merge_decisions()` 函数签名中新增可选参数 `main_force_env: str | None = None`
- [x] 4.2 实现 `_apply_main_force_weights(weights, main_force_env)` 权重修正函数，在 Scenario Priority Filter 之后、weighted_score 计算之前调用
- [x] 4.3 实现五种阶段的权重修正规则：accumulation（wyckoff+10%, mom-10%）、markup（mom+10%, chan-5%）、distribution（wyckoff+10%, chan-10%, mom-5%）、markdown（三路均下调）、unknown（不变）
- [x] 4.4 修正后重新归一化，确保三路权重之和为 1.0
- [x] 4.5 在 merge_decisions() 返回结果中新增 `main_force_env` 字段
- [x] 4.6 在 `_log_fusion()` 日志输出中包含 main_force_env 字段

## 5. 复盘输出集成

- [x] 5.1 在复盘输出脚本中新增 `format_main_force_section(result)` 函数，生成「主力行为」段落
- [x] 5.2 实现阶段名称中文映射：accumulation→吸筹期、testing→试盘期、markup→拉升期、distribution→派发期、markdown→砸盘期
- [x] 5.3 实现近期趋势符号生成：近5日每日净流入/流出转为 ↑/↓ 符号序列
- [x] 5.4 实现派发/砸盘期的警告提示输出
- [x] 5.5 处理数据不可用时的降级输出（"资金流向数据暂不可用"）

## 6. 数据管线集成

- [ ] 6.1 在 `data_provider.py` 的 `MarketDataSourceController` 或 `load_market_snapshot` 中增加资金流向数据获取
- [ ] 6.2 在复盘/分析流程中调用 `detect_main_force_stage()` 并将结果传入 `merge_decisions()`
- [ ] 6.3 在 T0 分析流程中复用资金流向缓存数据（读缓存，不实时抓取）

## 7. 测试

- [x] 7.1 为 `fund_flow_data.py` 编写单元测试：API调用、特征计算、降级处理
- [x] 7.2 为 `main_force.py` 编写单元测试：五阶段检测规则、置信度计算、信号列表
- [x] 7.3 为融合层权重修正编写单元测试：各阶段权重修正正确性、归一化验证、无 main_force_env 时行为不变
- [ ] 7.4 集成测试：端到端从数据采集→行为识别→融合→输出
