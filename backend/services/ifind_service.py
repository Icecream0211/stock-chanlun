"""同花顺 iFinD SDK/HTTP 行情适配器（可选，失败时由上层回退）。"""
from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import math
import threading
import time
from datetime import datetime
from typing import Any

import httpx
import pandas as pd

import config
from utils import LRUCache

log = logging.getLogger(__name__)

_sdk: Any | None = None
_logged_in = False
_last_login_attempt = 0.0
_last_error: str | None = None
_login_lock = threading.RLock()
_http_access_token: str | None = None
_http_client: httpx.Client | None = None
_http_lock = threading.RLock()

_kline_cache = LRUCache(maxsize=256, ttl=300.0)
_minute_cache = LRUCache(maxsize=256, ttl=60.0)
_quote_cache = LRUCache(maxsize=32, ttl=15.0)


def _plain_code(code: str) -> str:
    value = str(code).strip().upper()
    if "." in value:
        value = value.split(".", 1)[0]
    if value.startswith(("SH", "SZ", "BJ")):
        value = value[2:]
    return value.zfill(6)


def to_ifind_code(code: str) -> str:
    """将纯代码或腾讯格式代码转换为 iFinD 代码。"""
    value = _plain_code(code)
    if value.startswith(("60", "68", "50", "51")):
        exchange = "SH"
    elif value.startswith(("4", "8")):
        exchange = "BJ"
    else:
        exchange = "SZ"
    return f"{value}.{exchange}"


def _get_sdk() -> Any | None:
    global _sdk, _last_error
    if _sdk is not None:
        return _sdk
    try:
        _sdk = importlib.import_module("iFinDPy")
        return _sdk
    except Exception as exc:
        _last_error = f"SDK 加载失败: {exc}"
        log.warning("[iFinD] %s", _last_error)
        return None


def _ensure_login() -> Any | None:
    """按需登录；失败后冷却 60 秒，避免并发分析重复冲击登录接口。"""
    global _logged_in, _last_login_attempt, _last_error
    if not config.IFIND_ENABLED:
        return None
    if not config.IFIND_USERNAME or not config.IFIND_PASSWORD:
        _last_error = "缺少 IFIND_USERNAME 或 IFIND_PASSWORD"
        return None

    with _login_lock:
        sdk = _get_sdk()
        if sdk is None:
            return None
        if _logged_in:
            return sdk
        now = time.monotonic()
        if now - _last_login_attempt < 60:
            return None
        _last_login_attempt = now
        try:
            result = sdk.THS_iFinDLogin(config.IFIND_USERNAME, config.IFIND_PASSWORD)
            # 官方说明 -201 为重复登录，仍可继续取数。
            if int(result) in (0, -201):
                _logged_in = True
                _last_error = None
                log.info("[iFinD] 登录成功")
                return sdk
            _last_error = f"登录失败，错误码 {result}"
        except Exception as exc:
            _last_error = f"登录异常: {exc}"
        log.warning("[iFinD] %s", _last_error)
        return None


def _http_enabled() -> bool:
    return bool(config.IFIND_ACCESS_TOKEN or config.IFIND_REFRESH_TOKEN)


def _get_http_client() -> httpx.Client:
    global _http_client
    with _http_lock:
        if _http_client is None:
            _http_client = httpx.Client(
                base_url="https://quantapi.51ifind.com",
                timeout=30.0,
                follow_redirects=True,
                trust_env=False,
            )
        return _http_client


def _get_http_access_token() -> str:
    global _http_access_token, _last_error
    if config.IFIND_ACCESS_TOKEN:
        return config.IFIND_ACCESS_TOKEN
    with _http_lock:
        if _http_access_token:
            return _http_access_token
        if not config.IFIND_REFRESH_TOKEN:
            raise RuntimeError("缺少 IFIND_REFRESH_TOKEN 或 IFIND_ACCESS_TOKEN")
        response = _get_http_client().post(
            "/api/v1/get_access_token",
            headers={
                "Content-Type": "application/json",
                "refresh_token": config.IFIND_REFRESH_TOKEN,
            },
        )
        response.raise_for_status()
        payload = response.json()
        token = (payload.get("data") or {}).get("access_token")
        if not token:
            message = payload.get("errmsg") or payload.get("message") or "未返回 access_token"
            raise RuntimeError(str(message))
        _http_access_token = str(token)
        _last_error = None
        return _http_access_token


def _http_post(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = _get_http_client().post(
        endpoint,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "access_token": _get_http_access_token(),
            "ifindlang": "cn",
        },
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise RuntimeError("iFinD HTTP 返回格式异常")
    return result


def _field(result: Any, name: str, default: Any = None) -> Any:
    if isinstance(result, dict):
        return result.get(name, default)
    return getattr(result, name, default)


def _result_ok(result: Any) -> bool:
    code = _field(result, "errorcode", _field(result, "errorCode", 0))
    try:
        return int(code or 0) == 0
    except (TypeError, ValueError):
        return False


def _tables_to_frame(tables: Any) -> pd.DataFrame:
    if isinstance(tables, dict):
        tables = [tables]
    if not isinstance(tables, list):
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    for item in tables:
        if not isinstance(item, dict):
            continue
        table = item.get("table", item.get("data", {}))
        try:
            frame = pd.DataFrame(table)
        except (TypeError, ValueError):
            continue
        if frame.empty:
            continue
        times = item.get("time")
        if "time" not in frame.columns and isinstance(times, list) and len(times) == len(frame):
            frame["time"] = times
        code = item.get("thscode") or item.get("THSCODE")
        if code and "thscode" not in frame.columns:
            frame["thscode"] = code
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _result_to_frame(result: Any) -> pd.DataFrame:
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (TypeError, ValueError):
            return pd.DataFrame()
    if not _result_ok(result):
        message = _field(result, "errmsg", "未知错误")
        raise RuntimeError(str(message))
    if isinstance(result, pd.DataFrame):
        frame = result.copy()
    else:
        data = _field(result, "data")
        if isinstance(data, pd.DataFrame):
            frame = data.copy()
        elif isinstance(data, (dict, list)):
            try:
                frame = pd.DataFrame(data)
            except (TypeError, ValueError):
                frame = pd.DataFrame()
        else:
            frame = pd.DataFrame()
        if frame.empty:
            frame = _tables_to_frame(_field(result, "tables"))

    if frame.empty:
        return frame
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()

    frame.columns = [str(col).strip().lower() for col in frame.columns]
    times = _field(result, "time")
    if not any(col in frame.columns for col in ("time", "date", "datetime")):
        if isinstance(times, (list, tuple)) and len(times) == len(frame):
            frame["time"] = list(times)
    codes = _field(result, "thscode")
    if "thscode" not in frame.columns and isinstance(codes, (list, tuple)):
        if len(codes) == len(frame):
            frame["thscode"] = list(codes)
        elif len(codes) == 1:
            frame["thscode"] = codes[0]
    return frame


def _first_column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    compact = {col.replace("_", "").lower(): col for col in frame.columns}
    for alias in aliases:
        key = alias.replace("_", "").lower()
        if key in compact:
            return compact[key]
    return None


def _normalize_kline(result: Any, limit: int) -> pd.DataFrame:
    frame = _result_to_frame(result)
    if frame.empty:
        return frame
    aliases = {
        "date": ("date", "time", "datetime", "tradetime", "index"),
        "open": ("open",),
        "close": ("close", "latest"),
        "high": ("high",),
        "low": ("low",),
        "volume": ("volume", "vol", "latestvolume"),
    }
    selected: dict[str, Any] = {}
    for target, candidates in aliases.items():
        source = _first_column(frame, candidates)
        if source is not None:
            selected[target] = frame[source]
    if not {"date", "open", "close", "high", "low"}.issubset(selected):
        return pd.DataFrame()
    normalized = pd.DataFrame(selected)
    if "volume" not in normalized:
        normalized["volume"] = 0.0
    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
    for column in ("open", "close", "high", "low", "volume"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized = normalized.dropna(subset=["date", "open", "close", "high", "low"])
    normalized = normalized.sort_values("date").drop_duplicates("date", keep="last")
    return normalized.tail(limit).reset_index(drop=True)


def _date_range(period: str, limit: int, start_date: str | None, end_date: str | None) -> tuple[datetime, datetime]:
    end = pd.to_datetime(end_date, errors="coerce") if end_date else pd.Timestamp.now()
    if pd.isna(end):
        end = pd.Timestamp.now()
    if start_date:
        start = pd.to_datetime(start_date, errors="coerce")
    else:
        if period == "daily":
            days = limit * 2 + 30
        elif period == "weekly":
            days = limit * 8 + 30
        elif period == "monthly":
            days = limit * 35 + 60
        else:
            interval = max(1, int(period))
            bars_per_day = max(1, 240 // interval)
            days = math.ceil(limit / bars_per_day * 2.2) + 7
        start = end - pd.Timedelta(days=days)
    if pd.isna(start):
        start = end - pd.Timedelta(days=limit * 2 + 30)
    return start.to_pydatetime(), end.to_pydatetime()


def get_ifind_kline(
    code: str,
    period: str = "daily",
    start_date: str | None = None,
    end_date: str | None = None,
    adjust: str = "qfq",
    limit: int = 500,
) -> pd.DataFrame:
    """使用 THS_HQ/THS_HF 获取统一格式 K 线。"""
    global _last_error
    if period not in ("daily", "weekly", "monthly", "1", "3", "5", "10", "15", "30", "60"):
        return pd.DataFrame()
    limit = max(20, min(int(limit), 2000))
    cache = _minute_cache if period.isdigit() else _kline_cache
    cache_key = f"{to_ifind_code(code)}:{period}:{adjust}:{start_date}:{end_date}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        result = cached.copy()
        result.attrs["data_source"] = "ifind"
        return result

    use_http = _http_enabled()
    sdk = None if use_http else _ensure_login()
    if not use_http and sdk is None:
        return pd.DataFrame()
    start, end = _date_range(period, limit, start_date, end_date)
    cps = {"qfq": "forward1", "hfq": "backward1"}.get(str(adjust).lower(), "no")
    ths_code = to_ifind_code(code)
    try:
        if period.isdigit():
            if use_http:
                raw = _http_post(
                    "/api/v1/high_frequency",
                    {
                        "codes": ths_code,
                        "indicators": "open,high,low,close,volume",
                        "starttime": start.strftime("%Y-%m-%d 09:15:00"),
                        "endtime": end.strftime("%Y-%m-%d 15:15:00"),
                        "functionpara": {
                            "CPS": cps,
                            "Fill": "Previous",
                            "Timeformat": "LocalTime",
                            "Interval": period,
                        },
                    },
                )
            else:
                query = getattr(sdk, "THS_HF", None) or getattr(sdk, "THS_HighFrequenceSequence", None)
                if query is None:
                    raise RuntimeError("当前 iFinDPy 不包含 THS_HF")
                params = f"CPS:{cps},Fill:Previous,timeformat:LocalTime,Interval:{period}"
                raw = query(
                    ths_code,
                    "open;high;low;close;volume",
                    params,
                    start.strftime("%Y-%m-%d 09:15:00"),
                    end.strftime("%Y-%m-%d 15:15:00"),
                )
        else:
            interval = {"daily": "D", "weekly": "W", "monthly": "M"}[period]
            if use_http:
                raw = _http_post(
                    "/api/v1/cmd_history_quotation",
                    {
                        "codes": ths_code,
                        "indicators": "open,high,low,close,volume",
                        "startdate": start.strftime("%Y-%m-%d"),
                        "enddate": end.strftime("%Y-%m-%d"),
                        "functionpara": {
                            "Interval": interval,
                            "CPS": cps,
                            "Fill": "Previous",
                        },
                    },
                )
            else:
                query = getattr(sdk, "THS_HQ", None) or getattr(sdk, "THS_HistoryQuotes", None)
                if query is None:
                    raise RuntimeError("当前 iFinDPy 不包含 THS_HQ")
                raw = query(
                    ths_code,
                    "open,high,low,close,volume",
                    f"Interval:{interval},CPS:{cps},Fill:Previous",
                    start.strftime("%Y-%m-%d"),
                    end.strftime("%Y-%m-%d"),
                )
        frame = _normalize_kline(raw, limit)
        if not frame.empty:
            _last_error = None
            cache.set(cache_key, frame.copy())
            frame.attrs["data_source"] = "ifind"
        return frame
    except Exception as exc:
        _last_error = f"K线获取失败: {exc}"
        log.warning("[iFinD] %s %s %s", _last_error, code, period)
        return pd.DataFrame()


def _normalize_quotes(result: Any, requested_codes: list[str]) -> pd.DataFrame:
    frame = _result_to_frame(result)
    if frame.empty:
        return frame
    aliases = {
        "代码": ("thscode", "code", "securitycode", "index"),
        "名称": ("name", "securityname", "secname"),
        "最新价": ("latest", "new", "close"),
        "今开": ("open",),
        "最高": ("high",),
        "最低": ("low",),
        "昨收": ("preclose", "prevclose"),
        "涨跌幅": ("changeratio", "changepct"),
        "成交量": ("latestvolume", "volume", "vol"),
        "成交额": ("latestamount", "amount"),
    }
    normalized = pd.DataFrame(index=frame.index)
    for target, candidates in aliases.items():
        source = _first_column(frame, candidates)
        if source is not None:
            normalized[target] = frame[source]
    if "代码" not in normalized and len(frame) == len(requested_codes):
        normalized["代码"] = requested_codes
    if "代码" not in normalized or "最新价" not in normalized:
        return pd.DataFrame()
    normalized["代码"] = normalized["代码"].map(_plain_code)
    for column in ("最新价", "今开", "最高", "最低", "昨收", "涨跌幅", "成交量", "成交额"):
        if column not in normalized:
            normalized[column] = None
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if "名称" not in normalized:
        normalized["名称"] = ""
    normalized = normalized.dropna(subset=["最新价"]).drop_duplicates("代码", keep="last")
    return normalized[["代码", "名称", "最新价", "涨跌幅", "成交量", "成交额", "今开", "最高", "最低", "昨收"]].reset_index(drop=True)


def get_ifind_realtime_quote(codes: list[str]) -> pd.DataFrame:
    """使用 THS_RQ 获取批量实时行情，名称/昨收等缺项由统一数据层补齐。"""
    global _last_error
    if not codes:
        return pd.DataFrame()
    normalized_codes = [_plain_code(code) for code in codes]
    cache_key = ",".join(sorted(normalized_codes))
    cached = _quote_cache.get(cache_key)
    if cached is not None:
        result = cached.copy()
        result.attrs["data_source"] = "ifind"
        return result
    use_http = _http_enabled()
    sdk = None if use_http else _ensure_login()
    if not use_http and sdk is None:
        return pd.DataFrame()
    try:
        if use_http:
            raw = _http_post(
                "/api/v1/real_time_quotation",
                {
                    "codes": ",".join(to_ifind_code(code) for code in normalized_codes),
                    "indicators": "open,high,low,latest,latestAmount,latestVolume",
                },
            )
        else:
            query = getattr(sdk, "THS_RQ", None) or getattr(sdk, "THS_RealtimeQuotes", None)
            if query is None:
                return pd.DataFrame()
            raw = query(
                ",".join(to_ifind_code(code) for code in normalized_codes),
                "open;high;low;latest;latestAmount;latestVolume",
                "",
            )
        frame = _normalize_quotes(raw, normalized_codes)
        if not frame.empty:
            _last_error = None
            _quote_cache.set(cache_key, frame.copy())
            frame.attrs["data_source"] = "ifind"
        return frame
    except Exception as exc:
        _last_error = f"实时行情获取失败: {exc}"
        log.warning("[iFinD] %s", _last_error)
        return pd.DataFrame()


def ifind_status() -> dict[str, Any]:
    try:
        sdk_installed = importlib.util.find_spec("iFinDPy") is not None
    except (ImportError, ValueError):
        sdk_installed = _sdk is not None
    return {
        "enabled": config.IFIND_ENABLED,
        "configured": bool(
            (config.IFIND_USERNAME and config.IFIND_PASSWORD)
            or config.IFIND_REFRESH_TOKEN
            or config.IFIND_ACCESS_TOKEN
        ),
        "transport": (
            "http"
            if _http_enabled()
            else "sdk"
            if config.IFIND_USERNAME and config.IFIND_PASSWORD
            else None
        ),
        "sdk_installed": sdk_installed,
        "logged_in": _logged_in,
        "last_error": _last_error,
        "cache": {
            "kline": _kline_cache.stats(),
            "minute": _minute_cache.stats(),
            "quote": _quote_cache.stats(),
        },
    }
