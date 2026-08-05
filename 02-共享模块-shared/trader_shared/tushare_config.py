"""Tushare 配置 — token 请用环境变量或本地文件，勿把密钥写入本文件并提交。

优先级见 tushare_client._get_token：
    TUSHARE_TOKEN 环境变量
    > tushare_config.local.py（gitignore）
    > skill config.json
    > 本文件 TUSHARE_TOKEN（应始终为空）

专属高权限网关文档见 tushare_config.example.py。
"""
from __future__ import annotations

# 留空；生产请设置环境变量 TUSHARE_TOKEN 或本地 tushare_config.local.py
TUSHARE_TOKEN = ""

# 默认走专属 Pro 网关（筹码等高权限接口）
TUSHARE_API_URL = "http://api.quicksync.cn"
# 实时报价生产仍优先腾讯/新浪；若走 tushare realtime，也指向同一专属域
TUSHARE_REALTIME_URL = "http://api.quicksync.cn"
