# -*- coding: utf-8 -*-
"""缠论渲染兼容入口：实现在 trader_shared.chanlun_render。"""
from __future__ import annotations

import sys

from trader_shared import chanlun_render as _impl

sys.modules[__name__] = _impl
