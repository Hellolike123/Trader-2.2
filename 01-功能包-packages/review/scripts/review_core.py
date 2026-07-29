# -*- coding: utf-8 -*-
"""复盘核心兼容入口：实现在 trader_shared.review_core。"""
from __future__ import annotations

import sys

from trader_shared import review_core as _impl

sys.modules[__name__] = _impl
