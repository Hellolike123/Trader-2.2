"""Tushare 配置 — token 请用环境变量或本地文件，勿把密钥写入本文件并提交。

优先级见 tushare_client._get_token：
    TUSHARE_TOKEN 环境变量
    > tushare_config.local.py（gitignore）
    > skill config.json
    > 本文件 TUSHARE_TOKEN（应始终为空）

获取 token: https://tushare.pro
示例见 tushare_config.example.py
"""
from __future__ import annotations

# 留空；生产请设置环境变量 TUSHARE_TOKEN 或本地 tushare_config.local.py
TUSHARE_TOKEN = ""

TUSHARE_API_URL = "https://fastapic.stockai888.top"
TUSHARE_REALTIME_URL = "https://realtime.stockai888.top"
