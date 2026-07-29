# -*- coding: utf-8 -*-
"""兼容旧 candidate_model：转发 portfolio_core（现位于 trader_shared）。"""
from __future__ import annotations

import sys

from trader_shared import portfolio_core as _impl

sys.modules[__name__] = _impl
