# -*- coding: utf-8 -*-
"""威科夫计划/渲染兼容入口：实现在 trader_shared.wyckoff_run。"""
from __future__ import annotations

import sys

from trader_shared import wyckoff_run as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
