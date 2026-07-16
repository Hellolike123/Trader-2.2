"""Tushare Pro 数据客户端（SDK + HTTP 双通道）。

主用 tushare SDK 走代理端点；SDK 初始化失败时降级到 HTTP 直调。
Token 从环境变量 TUSHARE_TOKEN 读取；未设置时所有查询返回空，不崩溃。

环境变量：
    TUSHARE_TOKEN       必填，Tushare Pro API token
    TUSHARE_API_URL     可选，默认 https://fastapic.stockai888.top（日线/资金流/板块等）
    TUSHARE_REALTIME_URL 可选，默认 https://realtime.stockai888.top（实时爬虫）

使用方式：
    from trader_shared.tushare_client import get_client
    client = get_client()
    df = client.query("daily", ts_code="688248.SH", start_date="20260701")
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
import warnings
from pathlib import Path
from typing import Any

# ── 配置 ──────────────────────────────────────────────────────────────────
_DEFAULT_API_URL = "https://fastapic.stockai888.top"
_DEFAULT_REALTIME_URL = "https://realtime.stockai888.top"
_MIN_INTERVAL = 0.6  # 100次/分钟 ≈ 0.6s/请求


def _get_token() -> str:
    # 优先级: 环境变量 > skill 包内 config.json > tushare_config.py > 空
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if token:
        return token
    # 尝试 skill 包内的 config.json（pack_all.py 打包时自动写入）
    _skill_root = Path(__file__).resolve().parent.parent.parent
    _cfg = _skill_root / "config.json"
    if _cfg.exists():
        try:
            cfg = json.loads(_cfg.read_text(encoding="utf-8"))
            t = str(cfg.get("tushare_token", "")).strip()
            if t:
                return t
        except Exception:
            pass
    try:
        from trader_shared.tushare_config import TUSHARE_TOKEN
        return str(TUSHARE_TOKEN).strip()
    except ImportError:
        return ""


def _get_api_url() -> str:
    # 优先环境变量，其次配置文件
    url = os.environ.get("TUSHARE_API_URL", "").strip()
    if url:
        return url
    try:
        from trader_shared.tushare_config import TUSHARE_API_URL
        return str(TUSHARE_API_URL).strip()
    except ImportError:
        return _DEFAULT_API_URL


def _get_realtime_url() -> str:
    # 优先环境变量，其次配置文件
    url = os.environ.get("TUSHARE_REALTIME_URL", "").strip()
    if url:
        return url
    try:
        from trader_shared.tushare_config import TUSHARE_REALTIME_URL
        return str(TUSHARE_REALTIME_URL).strip()
    except ImportError:
        return _DEFAULT_REALTIME_URL


def _probe_reachable(url: str, timeout: float = 3.0) -> bool:
    """快速探测 API 主机的 TCP 可达性（带硬超时，绝不挂死）。

    用于避免对不可达主机（如离线/被墙的代理端点）发起无 timeout 的
    requests 调用导致整个进程永久 hang。DNS 解析与 connect 均在独立线程中
    受 timeout 约束；线程在 timeout 内未结束一律视为不可达。
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    result: list[bool] = [False]

    def _attempt() -> None:
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            result[0] = True
        except Exception:
            result[0] = False

    probe_thread = threading.Thread(target=_attempt, daemon=True)
    probe_thread.start()
    probe_thread.join(timeout + 1.0)
    # 线程在超时内未结束 = 探测挂死 = 视为不可达
    return (not probe_thread.is_alive()) and result[0]


# ── TushareClient ─────────────────────────────────────────────────────────
class TushareClient:
    """Tushare Pro 数据客户端，SDK 优先 + HTTP 降级。"""

    def __init__(self) -> None:
        self._token = _get_token()
        self._api_url = _get_api_url()
        self._realtime_url = _get_realtime_url()
        self._pro: Any = None  # tushare pro_api 实例
        self._last_call: float = 0.0
        self._sdk_ok: bool = False
        self._http_ok: bool = False

        if not self._token:
            warnings.warn("[tushare] TUSHARE_TOKEN 未设置，Tushare 数据功能禁用")
            return

        # 快速可达性探测：避免对不可达主机发起无超时请求导致进程挂死
        if not _probe_reachable(self._api_url):
            warnings.warn(
                f"[tushare] API {self._api_url} 不可达，禁用 Tushare 数据通道（将 fallback 到腾讯）"
            )
            return

        # 尝试初始化 SDK
        try:
            import tushare as ts  # noqa: F811
            ts.set_token(self._token)
            self._pro = ts.pro_api()
            self._pro._DataApi__http_url = self._api_url  # type: ignore[attr-defined]
            self._sdk_ok = True
        except Exception as e:
            warnings.warn(f"[tushare] SDK 初始化失败，降级到 HTTP: {e}")
            self._pro = None

        # HTTP 可用性（import requests）
        try:
            import requests  # noqa: F401
            self._http_ok = True
        except ImportError:
            pass

    @property
    def available(self) -> bool:
        """是否可用（token 存在且至少一种通道可初始化）。"""
        return bool(self._token) and (self._sdk_ok or self._http_ok)

    def _rate_limit(self) -> None:
        """简单限速：确保两次调用间隔 ≥ _MIN_INTERVAL 秒。"""
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        self._last_call = time.monotonic()

    # ── 通用查询 ──────────────────────────────────────────────────────────
    def query(self, api_name: str, **params: Any) -> list[dict[str, Any]]:
        """通用 Tushare 接口查询。返回 list[dict]，失败返回 []。"""
        if not self.available:
            return []

        # SDK 优先
        if self._sdk_ok and self._pro is not None:
            try:
                self._rate_limit()
                func = getattr(self._pro, api_name, None)
                if func is None:
                    warnings.warn(f"[tushare] SDK 无此接口: {api_name}")
                    return []
                df = func(**params)
                if df is not None and len(df) > 0:
                    return df.to_dict(orient="records")
                return []
            except Exception as e:
                warnings.warn(f"[tushare] SDK {api_name} 失败，尝试 HTTP: {e}")
                # 降级到 HTTP

        # HTTP 降级
        return self._query_http(api_name, **params)

    def _query_http(self, api_name: str, **params: Any) -> list[dict[str, Any]]:
        """HTTP 直调降级。"""
        if not self._http_ok:
            return []
        try:
            import requests
            self._rate_limit()
            resp = requests.post(
                self._api_url,
                json={
                    "api_name": api_name,
                    "token": self._token,
                    "params": params,
                },
                timeout=30,
                headers={"Accept-Encoding": "gzip"},
                proxies={"http": None, "https": None},
            )
            data = resp.json()
            if data.get("code") != 0:
                msg = data.get("msg", "")
                warnings.warn(f"[tushare] HTTP {api_name} 错误: {msg}")
                return []
            items = data.get("data", {}).get("items", [])
            fields = data.get("data", {}).get("fields", [])
            if not items or not fields:
                return []
            return [dict(zip(fields, row)) for row in items]
        except Exception as e:
            warnings.warn(f"[tushare] HTTP {api_name} 失败: {e}")
            return []

    # ── 便捷方法 ──────────────────────────────────────────────────────────
    def query_daily(
        self, ts_code: str, start_date: str = "", end_date: str = ""
    ) -> list[dict[str, Any]]:
        """日线行情。ts_code 格式如 '688248.SH'。"""
        params: dict[str, Any] = {"ts_code": ts_code, "adj": "qfq"}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self.query("daily", **params)

    def query_moneyflow(
        self, ts_code: str, start_date: str = "", end_date: str = ""
    ) -> list[dict[str, Any]]:
        """个股资金流向。"""
        params: dict[str, Any] = {"ts_code": ts_code}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self.query("moneyflow", **params)

    def query_realtime(self, ts_codes: str) -> list[dict[str, Any]]:
        """实时行情（爬虫，走 realtime.stockai888.top）。

        ts_codes: 逗号分隔，如 '688248.SH,000001.SZ'
        """
        if not self.available or not self._sdk_ok:
            return []
        try:
            self._rate_limit()
            import os
            import tushare as ts
            from tushare.stock import cons as ct
            ct.verify_token_url = self._realtime_url
            # 用锁保证 NO_PROXY 设/改/还原原子化，并发/测试安全
            with _no_proxy_lock:
                _old_no_proxy = os.environ.get("NO_PROXY")
                try:
                    os.environ["NO_PROXY"] = "*"
                    df = ts.realtime_quote(ts_code=ts_codes)
                finally:
                    if _old_no_proxy is None:
                        os.environ.pop("NO_PROXY", None)
                    else:
                        os.environ["NO_PROXY"] = _old_no_proxy
            if df is not None and len(df) > 0:
                return df.to_dict(orient="records")
            return []
        except Exception as e:
            warnings.warn(f"[tushare] realtime_quote 失败: {e}")
            return []

    def query_concept(self) -> list[dict[str, Any]]:
        """概念板块列表。"""
        return self.query("concept")

    def query_concept_detail(self, concept_id: str) -> list[dict[str, Any]]:
        """概念板块成分股。"""
        return self.query("concept_detail", id=concept_id)

    def query_ths_index(self, index_type: str = "N") -> list[dict[str, Any]]:
        """同花顺概念/行业指数。type: 'N'=概念, 'I'=行业。"""
        return self.query("ths_index", exchange="A", type=index_type)

    def query_ths_daily(
        self, ts_code: str, start_date: str = "", end_date: str = ""
    ) -> list[dict[str, Any]]:
        """同花顺板块指数日线。"""
        params: dict[str, Any] = {"ts_code": ts_code}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self.query("ths_daily", **params)

    def query_ths_member(self, ts_code: str) -> list[dict[str, Any]]:
        """同花顺板块成分股。"""
        return self.query("ths_member", ts_code=ts_code)

    def query_cyq_perf(
        self, ts_code: str, start_date: str = "", end_date: str = ""
    ) -> list[dict[str, Any]]:
        """筹码分布。"""
        params: dict[str, Any] = {"ts_code": ts_code}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self.query("cyq_perf", **params)

    def query_cyq_chips(
        self, ts_code: str, trade_date: str
    ) -> list[dict[str, Any]]:
        """每日筹码。"""
        return self.query("cyq_chips", ts_code=ts_code, trade_date=trade_date)

    def query_index_classify(self, src: str = "SW") -> list[dict[str, Any]]:
        """行业分类。src: 'SW'=申万。"""
        return self.query("index_classify", src=src, level="L2")


# ── 全局单例 ──────────────────────────────────────────────────────────────
_client: TushareClient | None = None

# NO_PROXY 全局切换的并发锁：将「设代理→调用→还原」包成原子区，
# 避免并发 realtime_quote 时 os.environ["NO_PROXY"] 相互踩踏。
_no_proxy_lock = threading.Lock()


def get_client() -> TushareClient:
    """获取全局 TushareClient 单例。"""
    global _client
    if _client is None:
        _client = TushareClient()
    return _client


def reset_client() -> None:
    """重置全局单例（测试用）。"""
    global _client
    _client = None
