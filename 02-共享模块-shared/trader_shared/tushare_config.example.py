"""Tushare 本地配置示例。

推荐：
    export TUSHARE_TOKEN='你的token'
    export TUSHARE_API_URL='http://api.quicksync.cn'
    export TUSHARE_REALTIME_URL='http://api.quicksync.cn'

或复制本文件为同目录下的 ``tushare_config.local.py`` 后填写。

勿把密钥写进仓库内的 ``tushare_config.py``。
"""
from __future__ import annotations

TUSHARE_TOKEN = ""

# 专属高权限网关（推荐）；如需官方域可改回 https://api.tushare.pro
TUSHARE_API_URL = "http://api.quicksync.cn"
TUSHARE_REALTIME_URL = "http://api.quicksync.cn"
