# -*- coding: utf-8 -*-
"""T0 核心兼容入口：实现在 trader_shared.t0_core。"""
from __future__ import annotations

import sys

from trader_shared import t0_core as _impl

sys.modules[__name__] = _impl
