# -*- coding: utf-8 -*-
"""威科夫渲染兼容入口：实现在 trader_shared.wyckoff_render。"""
from __future__ import annotations

import sys

from trader_shared import wyckoff_render as _impl

sys.modules[__name__] = _impl
