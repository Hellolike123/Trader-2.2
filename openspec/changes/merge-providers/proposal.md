## Why

`data_provider.py` 有三个 Provider 类（MootdxProvider 130行、TencentSinaProvider 120行、AkShareProvider 200行），共 712 行。其中 MootdxProvider 和 TencentSinaProvider 99% 代码相同（仅 `name` 和 `fetch_ticks` 不同），三个类全部委托给 `light_data.py` 的函数。合并为一个 UnifiedProvider 可消除 460 行重复代码。

## What Changes

- 合并三个 Provider 类为一个 `UnifiedProvider`，通过 `backend` 参数切换数据源
- 保留 `DataProvider` 协议接口不变
- 保留 AkShare 的独立逻辑（`_to_standard_bar`）作为私有方法
- 删除 `MootdxProvider` 和 `TencentSinaProvider` 类
- 更新 `get_provider()` 返回 `UnifiedProvider`

## Impact

- 修改文件：`trader_shared/data_provider.py`
- 无新增文件
- 向后兼容：`get_provider()` 返回的对象仍然实现 `DataProvider` 协议
