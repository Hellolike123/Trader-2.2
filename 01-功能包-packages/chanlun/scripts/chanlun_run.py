# -*- coding: utf-8 -*-
"""缠论编排兼容入口：实现在 trader_shared.chanlun_run。"""
from __future__ import annotations

import sys

from trader_shared import chanlun_run as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
