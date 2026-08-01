# -*- coding: utf-8 -*-
"""T0 账户兼容入口：实现在 trader_shared.t0_account。"""
from __future__ import annotations

import sys

from trader_shared import t0_account as _impl

sys.modules[__name__] = _impl
