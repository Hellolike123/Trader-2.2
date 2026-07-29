# -*- coding: utf-8 -*-
"""复盘渲染兼容入口：实现在 trader_shared.review_render。"""
from __future__ import annotations

import sys

from trader_shared import review_render as _impl

sys.modules[__name__] = _impl
