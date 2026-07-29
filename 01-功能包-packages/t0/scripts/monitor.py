# -*- coding: utf-8 -*-
"""T0 盯盘兼容入口：实现在 trader_shared.t0_monitor。

用 sys.modules 替换本模块身份，保证 monkeypatch monitor.xxx 作用在真实实现上。
"""
from __future__ import annotations

import sys

from trader_shared import t0_monitor as _impl

sys.modules[__name__] = _impl
