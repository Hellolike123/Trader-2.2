# -*- coding: utf-8 -*-
"""兼容旧 review_model：转发 review_core（现位于 trader_shared）。"""
from __future__ import annotations

import sys

from trader_shared import review_core as _impl

sys.modules[__name__] = _impl
