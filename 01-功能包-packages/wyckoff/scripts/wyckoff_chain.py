# -*- coding: utf-8 -*-
"""威科夫吸筹链兼容入口：实现在 trader_shared.wyckoff_chain。"""
from __future__ import annotations

import sys

from trader_shared import wyckoff_chain as _impl

sys.modules[__name__] = _impl
