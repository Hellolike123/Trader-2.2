"""Test bootstrap for trader_shared.

Ensures the shared package root is importable regardless of pytest's
invocation directory, so `import trader_shared` (and its submodules)
resolve without relying on the legacy scripts/ path injection.
"""
import sys
from pathlib import Path

# 02-共享模块-shared/ — parent of this tests/ dir
_SHARED_ROOT = Path(__file__).resolve().parent.parent
if str(_SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHARED_ROOT))

import os

import pytest


@pytest.fixture(autouse=True, scope="function")
def _isolate_data_provider():
    """每个测试后恢复 data_provider 全局状态，隔离 set_provider() 泄漏。

    set_provider() 既改写模块级 _PROVIDER，又写 os.environ["TRADER_DATA_PROVIDER"]，
    二者均非 monkeypatch 可还原（monkeypatch 只能还原函数/属性，还原不了被调用写的值）。
    若不留这道闸，golden/adr002/render 等测试会互相污染 _PROVIDER 与 env，导致批量
    运行时后续测试行为畸变（hang/崩溃），而单独跑却全过——典型跨文件全局状态污染。
    """
    import trader_shared.data_provider as _dp

    saved_provider = _dp._provider
    saved_env = os.environ.get("TRADER_DATA_PROVIDER")
    try:
        yield
    finally:
        _dp._provider = saved_provider
        if saved_env is None:
            os.environ.pop("TRADER_DATA_PROVIDER", None)
        else:
            os.environ["TRADER_DATA_PROVIDER"] = saved_env
