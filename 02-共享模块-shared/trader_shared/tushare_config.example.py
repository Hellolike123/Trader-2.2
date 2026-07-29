"""Tushare 配置示例。

推荐（勿把真实 token 写入 git）：
    export TUSHARE_TOKEN='你的token'

或复制本文件为同目录下的 ``tushare_config.local.py`` 后填写
（已在 .gitignore，勿提交）。

勿把密钥写进仓库内的 ``tushare_config.py``。
"""
from __future__ import annotations

TUSHARE_TOKEN = ""

TUSHARE_API_URL = "https://fastapic.stockai888.top"
TUSHARE_REALTIME_URL = "https://realtime.stockai888.top"
