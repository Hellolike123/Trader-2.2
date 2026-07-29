# -*- coding: utf-8 -*-
"""T0 ICT 兼容入口：实现在 trader_shared.t0_ict_execution。"""
from __future__ import annotations

import sys

from trader_shared import t0_ict_execution as _impl

sys.modules[__name__] = _impl
