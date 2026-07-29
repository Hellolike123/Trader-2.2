# -*- coding: utf-8 -*-
"""T0 价位引擎兼容入口：实现在 trader_shared.t0_price_point_engine。"""
from __future__ import annotations

import sys

from trader_shared import t0_price_point_engine as _impl

sys.modules[__name__] = _impl
