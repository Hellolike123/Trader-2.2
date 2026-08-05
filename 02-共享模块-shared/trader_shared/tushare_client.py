"""Tushare Pro 数据客户端（SDK + HTTP 双通道）。

默认走专属网关 ``http://api.quicksync.cn``（高权限筹码等）；HTTP 优先，``TUSHARE_SDK_FIRST=1`` 可改 SDK 优先。
Token：环境变量 / tushare_config.local.py；未设置时查询返回空，不崩溃。

环境变量：
    TUSHARE_TOKEN       必填，Tushare Pro API token
    TUSHARE_API_URL     可选，默认 http://api.quicksync.cn
    TUSHARE_REALTIME_URL 可选，默认 http://api.quicksync.cn
    TUSHARE_SDK_FIRST   可选，1=SDK 优先；默认 0（HTTP 优先）

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
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# ── 配置 ──────────────────────────────────────────────────────────────────
_DEFAULT_API_URL = "http://api.quicksync.cn"
_DEFAULT_REALTIME_URL = "http://api.quicksync.cn"
# 官方也有频控；进程内轻微节流，避免连打触发分钟限额
_MIN_INTERVAL = 0.35
_RATE_LOCK = threading.Lock()
_LAST_CALL_MONO = 0.0


def _sdk_first_enabled() -> bool:
    return os.environ.get("TUSHARE_SDK_FIRST", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _global_rate_limit() -> None:
    """进程级限速（多 Client / 多线程共用）。"""
    global _LAST_CALL_MONO
    with _RATE_LOCK:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _LAST_CALL_MONO)
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL_MONO = time.monotonic()


def bypass_http_proxy_for_market() -> None:
    """Clear process HTTP(S) proxy so Tushare/腾讯不被系统代理隧道 403。

    Agent / IDE 沙箱常注入 http_proxy；对 api.tushare.pro 探测与 POST 会误伤。
    行情通道一律直连。可用 TRADER_KEEP_HTTP_PROXY=1 保留代理（调试用）。
    """
    if os.environ.get("TRADER_KEEP_HTTP_PROXY", "").strip() in ("1", "true", "True", "yes"):
        return
    for key in (
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "all_proxy",
        "ALL_PROXY",
    ):
        os.environ.pop(key, None)
    # 兜底：即便残留代理库读到旧值，也让直连主机走 NO_PROXY
    for key in ("NO_PROXY", "no_proxy"):
        cur = os.environ.get(key, "")
        if "*" in cur:
            continue
        extra = "api.tushare.pro,.tushare.pro,api.quicksync.cn,.quicksync.cn,run.quicksync.cn,run.tushare.xyz,qt.gtimg.cn,web.ifzq.gtimg.cn,.gtimg.cn,.qq.com,money.finance.sina.com.cn,finance.sina.com.cn,suggest3.sinajs.cn,.sina.com.cn,.sinajs.cn,.eastmoney.com"
        os.environ[key] = f"{cur},{extra}" if cur else extra


def _resolve_proxies() -> dict | None:
    """代理策略。

    默认返回 {"http": None, "https": None} 强制直连（绕过会 403 的沙箱注入代理，
    见 bypass_http_proxy_for_market）。

    设 TRADER_KEEP_HTTP_PROXY=1 时返回 None，让 requests 跟随环境 http_proxy/https_proxy
    （用于必须走代理才能出网的沙箱，如当前 WorkBuddy 执行环境）。
    """
    if os.environ.get("TRADER_KEEP_HTTP_PROXY", "").strip() in ("1", "true", "True", "yes"):
        return None
    return {"http": None, "https": None}


def _load_local_tushare_config():
    """加载同目录 ``tushare_config.local.py``（文件名含点，用 importlib）。"""
    local_path = Path(__file__).resolve().parent / "tushare_config.local.py"
    if not local_path.is_file():
        return None
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "trader_shared_tushare_config_local", local_path
        )
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _load_local_tushare_token() -> str:
    """从本地配置读 token。"""
    mod = _load_local_tushare_config()
    if mod is None:
        return ""
    return str(getattr(mod, "TUSHARE_TOKEN", "") or "").strip()


def _skill_config_dict() -> dict[str, Any]:
    """读取 skill 包 config.json（pack_all 写入；仓内通常不存在）。"""
    _skill_root = Path(__file__).resolve().parent.parent.parent
    _cfg = _skill_root / "config.json"
    if not _cfg.exists():
        return {}
    try:
        cfg = json.loads(_cfg.read_text(encoding="utf-8"))
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _get_token() -> str:
    # 优先级: 环境变量 > 本地 tushare_config.local.py > skill config.json > tushare_config.py > 空
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if token:
        return token
    local_token = _load_local_tushare_token()
    if local_token:
        return local_token
    # 尝试 skill 包内的 config.json（pack_all.py 打包时自动写入；勿把含密钥的 zip 公开分发）
    cfg = _skill_config_dict()
    t = str(cfg.get("tushare_token", "") or "").strip()
    if t:
        return t
    try:
        from trader_shared.tushare_config import TUSHARE_TOKEN
        return str(TUSHARE_TOKEN).strip()
    except ImportError:
        return ""


def _get_api_url() -> str:
    # 优先环境变量，其次本地 local 配置，再 skill config / 共享配置，最后默认专属网关
    url = os.environ.get("TUSHARE_API_URL", "").strip()
    if url:
        return url
    mod = _load_local_tushare_config()
    if mod is not None:
        local_url = str(getattr(mod, "TUSHARE_API_URL", "") or "").strip()
        if local_url:
            return local_url
    cfg = _skill_config_dict()
    cfg_url = str(cfg.get("tushare_api_url", "") or "").strip()
    if cfg_url:
        return cfg_url
    try:
        from trader_shared.tushare_config import TUSHARE_API_URL
        return str(TUSHARE_API_URL).strip() or _DEFAULT_API_URL
    except ImportError:
        return _DEFAULT_API_URL


def _get_realtime_url() -> str:
    # 优先环境变量，其次本地 local 配置，再 skill config / 共享配置，最后默认专属网关
    url = os.environ.get("TUSHARE_REALTIME_URL", "").strip()
    if url:
        return url
    mod = _load_local_tushare_config()
    if mod is not None:
        local_url = str(getattr(mod, "TUSHARE_REALTIME_URL", "") or "").strip()
        if local_url:
            return local_url
    cfg = _skill_config_dict()
    cfg_url = str(cfg.get("tushare_realtime_url", "") or cfg.get("tushare_api_url", "") or "").strip()
    if cfg_url:
        return cfg_url
    try:
        from trader_shared.tushare_config import TUSHARE_REALTIME_URL
        return str(TUSHARE_REALTIME_URL).strip() or _DEFAULT_REALTIME_URL
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

        # 专属网关/官方域都优先直连，避免 socks5h 代理缺依赖把整通道打挂
        try:
            bypass_http_proxy_for_market()
        except Exception:
            pass

        # 快速可达性探测：避免对不可达主机发起无超时请求导致进程挂死
        if not _probe_reachable(self._api_url):
            warnings.warn(
                f"[tushare] API {self._api_url} 不可达，禁用 Tushare 数据通道（将 fallback 到腾讯）"
            )
            return

        # 尝试初始化 SDK
        try:
            import tushare as ts  # noqa: F811
            try:
                import tushare.pro.client as _ts_client  # type: ignore
                # 与专属文档一致：改 DataApi 默认网关，避免仍打官方域名
                _ts_client.DataApi._DataApi__http_url = self._api_url  # type: ignore[attr-defined]
            except Exception:
                pass
            ts.set_token(self._token)
            self._pro = ts.pro_api(self._token)
            try:
                self._pro._DataApi__http_url = self._api_url  # type: ignore[attr-defined]
            except Exception:
                pass
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
        """进程级限速（兼容旧调用点）。"""
        _global_rate_limit()
        self._last_call = time.monotonic()

    def _query_sdk(self, api_name: str, **params: Any) -> list[dict[str, Any]] | None:
        """SDK 查询。成功非空返回 list；失败/空表返回 None（交给 HTTP）。"""
        if not self._sdk_ok or self._pro is None:
            return None
        try:
            self._rate_limit()
            func = getattr(self._pro, api_name, None)
            if func is None:
                return None
            df = func(**params)
            if df is not None and len(df) > 0:
                return df.to_dict(orient="records")
            return None
        except Exception as e:
            warnings.warn(f"[tushare] SDK {api_name} 失败，尝试 HTTP: {e}")
            return None

    # ── 通用查询 ──────────────────────────────────────────────────────────
    def query(self, api_name: str, **params: Any) -> list[dict[str, Any]]:
        """通用 Tushare 接口查询。返回 list[dict]，失败返回 []。"""
        if not self.available:
            return []

        # 默认 HTTP 优先；TUSHARE_SDK_FIRST=1 时 SDK → HTTP
        if _sdk_first_enabled():
            sdk_rows = self._query_sdk(api_name, **params)
            if sdk_rows is not None:
                return sdk_rows
            return self._query_http(api_name, **params)

        http_rows = self._query_http(api_name, **params)
        if http_rows:
            return http_rows
        sdk_rows = self._query_sdk(api_name, **params)
        return sdk_rows if sdk_rows is not None else []

    def _query_http(self, api_name: str, **params: Any) -> list[dict[str, Any]]:
        """HTTP 直调；遇分钟限流睡 1s 再试一次。"""
        if not self._http_ok:
            return []
        try:
            import requests
        except ImportError:
            return []

        last_msg = ""
        for attempt in range(2):
            try:
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
                    proxies=_resolve_proxies(),
                )
                data = resp.json()
                if data.get("code") != 0:
                    last_msg = str(data.get("msg", "") or "")
                    if attempt == 0 and ("超限" in last_msg or "限流" in last_msg):
                        time.sleep(1.0)
                        continue
                    warnings.warn(f"[tushare] HTTP {api_name} 错误: {last_msg}")
                    return []
                items = data.get("data", {}).get("items", [])
                fields = data.get("data", {}).get("fields", [])
                if not items or not fields:
                    return []
                return [dict(zip(fields, row)) for row in items]
            except Exception as e:
                warnings.warn(f"[tushare] HTTP {api_name} 失败: {e}")
                return []
        if last_msg:
            warnings.warn(f"[tushare] HTTP {api_name} 错误: {last_msg}")
        return []

    # ── 便捷方法 ──────────────────────────────────────────────────────────
    def query_daily(
        self, ts_code: str, start_date: str = "", end_date: str = ""
    ) -> list[dict[str, Any]]:
        """日线行情。ts_code 格式如 '688248.SH'。

        注意：官方 ``daily`` 为未复权；复权请走 adj_factor / 下游字段，勿在此硬塞 adj。
        """
        params: dict[str, Any] = {"ts_code": ts_code}
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
        """实时行情（tushare realtime_quote；生产现价仍优先腾讯）。

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
            # 持锁临时 NO_PROXY=*，finally 还原（见 _no_proxy_star）
            with _no_proxy_star():
                df = ts.realtime_quote(ts_code=ts_codes)
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
        self,
        ts_code: str,
        trade_date: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> list[dict[str, Any]]:
        """每日筹码 / 筹码峰分布。

        兼容两种调用：
        - trade_date=YYYYMMDD：单日逐价位
        - start_date/end_date：区间（专属网关文档示例）
        """
        params: dict[str, Any] = {"ts_code": ts_code}
        if trade_date:
            params["trade_date"] = trade_date
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self.query("cyq_chips", **params)

    
    def query_stk_holdernumber(
        self, ts_code: str, start_date: str = "", end_date: str = ""
    ) -> list[dict[str, Any]]:
        """股东户数。"""
        params: dict[str, Any] = {"ts_code": ts_code}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self.query("stk_holdernumber", **params)

    def query_share_float(
        self, ts_code: str, start_date: str = "", end_date: str = ""
    ) -> list[dict[str, Any]]:
        """限售解禁 / 流通股本变动。"""
        params: dict[str, Any] = {"ts_code": ts_code}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self.query("share_float", **params)

    def query_margin_detail(
        self, ts_code: str = "", trade_date: str = "", start_date: str = "", end_date: str = ""
    ) -> list[dict[str, Any]]:
        """融资融券交易明细。"""
        params: dict[str, Any] = {}
        if ts_code:
            params["ts_code"] = ts_code
        if trade_date:
            params["trade_date"] = trade_date
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self.query("margin_detail", **params)

    def query_moneyflow_hsgt(
        self, start_date: str = "", end_date: str = "", trade_date: str = ""
    ) -> list[dict[str, Any]]:
        """沪深港通资金流向。"""
        params: dict[str, Any] = {}
        if trade_date:
            params["trade_date"] = trade_date
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self.query("moneyflow_hsgt", **params)

    def query_index_classify(self, src: str = "SW") -> list[dict[str, Any]]:
        """行业分类。src: 'SW'=申万。"""
        return self.query("index_classify", src=src, level="L2")


# ── 全局单例 ──────────────────────────────────────────────────────────────
_client: TushareClient | None = None

# NO_PROXY 全局切换的并发锁：将「设代理→调用→还原」包成原子区，
# 避免并发 realtime_quote 时 os.environ["NO_PROXY"] 相互踩踏。
# 说明：tushare SDK 无独立 proxy 参数时只能临时改 env；锁 + finally 还原已防泄漏。
_no_proxy_lock = threading.Lock()


@contextmanager
def _no_proxy_star():
    """临时 NO_PROXY=*（持锁）；退出时还原，不残留。"""
    with _no_proxy_lock:
        old = os.environ.get("NO_PROXY")
        try:
            os.environ["NO_PROXY"] = "*"
            yield
        finally:
            if old is None:
                os.environ.pop("NO_PROXY", None)
            else:
                os.environ["NO_PROXY"] = old


def get_client() -> TushareClient:
    """获取全局 TushareClient 单例。"""
    global _client
    bypass_http_proxy_for_market()
    if _client is None:
        _client = TushareClient()
    return _client


def reset_client() -> None:
    """重置全局单例（测试用）。"""
    global _client
    _client = None
