# -*- coding: utf-8 -*-
"""仓位轮动核心兼容入口：实现在 trader_shared.portfolio_core。"""
from __future__ import annotations

import sys

from trader_shared import portfolio_core as _impl

sys.modules[__name__] = _impl
