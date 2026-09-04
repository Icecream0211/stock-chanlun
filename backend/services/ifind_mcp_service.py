"""iFinD Streamable HTTP MCP 最终兜底适配器。

凭证与服务地址只从本地环境变量读取。这里不替代常规行情源，仅在公网接口
全部不可用时，为股票搜索、热门股、新闻与主要指数提供最后一级降级。
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from typing import Any

import httpx
import pandas as pd

import config
from utils import LRUCache

log = logging.getLogger(__name__)

_PROTOCOL_VERSION = "2025-03-26"
_call_lock = threading.RLock()
_last_error: str | None = None
_cache = LRUCache(maxsize=64, ttl=120.0)


def _configured(url: str) -> bool:
    return bool(config.IFIND_MCP_ENABLED and config.IFIND_MCP_AUTH_TOKEN and url)


def _response_json(response: httpx.Response) -> dict[str, Any]:
    """兼容 application/json 与 Streamable HTTP 的 SSE 单事件响应。"""
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        result = response.json()
        if not isinstance(result, dict):
            raise RuntimeError("iFinD MCP 返回格式异常")
        return result
    for line in response.text.splitlines():
        if line.startswith("data:"):
            result = json.loads(line[5:].strip())
            if isinstance(result, dict):
                return result
    raise RuntimeError("iFinD MCP SSE 未返回数据事件")


def _call_tool(url: str, tool_name: str, arguments: dict[str, Any]) -> Any:
    global _last_error
    if not _configured(url):
        return None
    headers = {
        "Authorization": config.IFIND_MCP_AUTH_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    try:
        # 兜底调用频率低；每次建立独立会话可避免跨线程复用过期 session。
        with _call_lock, httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            trust_env=False,
        ) as client:
            init = client.post(
                url,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": _PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "stock-chanlun", "version": "0.2.0"},
                    },
                },
            )
            init.raise_for_status()
            init_body = _response_json(init)
            if init_body.get("error"):
                raise RuntimeError(str(init_body["error"]))
            session_id = init.headers.get("mcp-session-id")
            if session_id:
                headers["Mcp-Session-Id"] = session_id
            ready = client.post(
                url,
                headers=headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
            ready.raise_for_status()
            response = client.post(
                url,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                },
            )
            response.raise_for_status()
            body = _response_json(response)
        if body.get("error"):
            raise RuntimeError(str(body["error"]))
        result = body.get("result") or {}
        if result.get("isError"):
            raise RuntimeError("iFinD MCP 工具调用失败")
        text = "\n".join(
            str(item.get("text", ""))
            for item in result.get("content", [])
            if item.get("type") == "text"
        ).strip()
        payload: Any = json.loads(text) if text else None
        if isinstance(payload, dict) and payload.get("code") not in (None, 0, 1):
            raise RuntimeError(str(payload.get("msg") or payload.get("subMsg") or "调用失败"))
        data = payload.get("data") if isinstance(payload, dict) else payload
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (TypeError, ValueError):
                pass
        _last_error = None
        return data
    except Exception as exc:
        _last_error = f"{tool_name} 调用失败: {exc}"
        log.warning("[iFinD MCP] %s", _last_error)
        return None


def _markdown_table(text: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip().startswith("|")]
    for index in range(len(lines) - 2):
        headers = [cell.strip() for cell in lines[index].strip("|").split("|")]
        separator = [cell.strip() for cell in lines[index + 1].strip("|").split("|")]
        if not headers or len(headers) != len(separator):
            continue
        if not all(cell and set(cell) <= {"-", ":"} for cell in separator):
            continue
        records: list[dict[str, str]] = []
        for line in lines[index + 2 :]:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != len(headers):
                break
            records.append(dict(zip(headers, cells)))
        return records
    return []


def _pick(record: dict[str, str], exact: tuple[str, ...], prefix: tuple[str, ...] = ()) -> str:
    for key in exact:
        if record.get(key):
            return record[key]
    for key, value in record.items():
        if value and any(key.startswith(start) for start in prefix):
            return value
    return ""


def _plain_code(value: str) -> str:
    return str(value or "").strip().split(".", 1)[0].zfill(6)


def search_stocks(keyword: str, limit: int = 20) -> pd.DataFrame:
    key = f"mcp-search:{keyword.strip()}:{limit}"
    cached = _cache.get(key)
    if cached is not None:
        return cached.copy()
    data = _call_tool(
        config.IFIND_MCP_STOCK_URL,
        "get_stock_info",
        {"query": f"{keyword.strip()}的股票简称、A股股票代码、公司中文名称"},
    )
    rows = _markdown_table(data.get("answer", "") if isinstance(data, dict) else "")
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        code = _plain_code(_pick(row, ("股票代码", "证券代码")))
        name = _pick(row, ("股票简称", "证券简称"))
        if len(code) != 6 or not code.isdigit() or not name or code in seen:
            continue
        seen.add(code)
        records.append({"code": code, "name": name})
    frame = pd.DataFrame(records[:limit], columns=["code", "name"])
    if not frame.empty:
        frame.attrs["data_source"] = "ifind_mcp"
        _cache.set(key, frame.copy())
    return frame


def get_hot_stocks(limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 50))
    key = f"mcp-hot:{limit}"
    cached = _cache.get(key)
    if cached is not None:
        return list(cached)
    data = _call_tool(
        config.IFIND_MCP_STOCK_URL,
        "search_stocks",
        {"query": f"A股今日涨跌幅从高到低排名前{limit}，返回股票代码、股票简称、最新价和涨跌幅"},
    )
    rows = _markdown_table(data.get("answer", "") if isinstance(data, dict) else "")
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:limit], 1):
        code = _plain_code(_pick(row, ("股票代码", "证券代码")))
        name = _pick(row, ("股票简称", "证券简称"))
        try:
            change_pct = float(_pick(row, ("涨跌幅",), ("涨跌幅:",)))
        except (TypeError, ValueError):
            change_pct = 0.0
        try:
            price = float(_pick(row, ("最新价", "收盘价"), ("最新价:", "收盘价:")))
        except (TypeError, ValueError):
            price = 0.0
        if len(code) != 6 or not code.isdigit() or not name:
            continue
        result.append(
            {
                "code": code,
                "name": name,
                "change_pct": round(change_pct, 2),
                "price": round(price, 2),
                "volume": 0.0,
                "amount": 0.0,
                "rank": index,
                "data_source": "ifind_mcp",
            }
        )
    if result:
        _cache.set(key, list(result))
    return result


def get_news(limit: int = 10) -> list[dict[str, str]]:
    limit = max(1, min(int(limit), 20))
    key = f"mcp-news:{limit}"
    cached = _cache.get(key)
    if cached is not None:
        return list(cached)
    data = _call_tool(
        config.IFIND_MCP_NEWS_URL,
        "search_trending_news",
        {"time_scope": "24小时", "sensitive": "全部", "size": limit},
    )
    items = data.get("result", []) if isinstance(data, dict) else []
    result: list[dict[str, str]] = []
    for item in items[:limit]:
        title = str(item.get("资讯标题", "") or "").strip()
        if not title:
            continue
        result.append(
            {
                "title": title,
                "time": str(item.get("发布时间", "") or ""),
                "source": str(item.get("信息来源", "") or "iFinD"),
                "url": str(item.get("URL", "") or ""),
                "digest": str(item.get("资讯内容", "") or "").strip()[:120],
                "data_source": "ifind_mcp",
            }
        )
    if result:
        _cache.set(key, list(result))
    return result


def get_market_overview() -> dict[str, Any]:
    key = "mcp-market-overview"
    cached = _cache.get(key)
    if cached is not None:
        return dict(cached)
    data = _call_tool(
        config.IFIND_MCP_INDEX_URL,
        "index_highfreq_quotes",
        {
            "symbols": "000001.SH,399001.SZ,399006.SZ,000688.SH,000300.SH,000905.SH",
            "indicators": "最新价,涨跌幅,上涨家数,下跌家数",
            "data_mode": "real_time",
        },
    )
    tables = data.get("tables", []) if isinstance(data, dict) else []
    if not tables or len(tables) < 2:
        return {}
    headers = [str(value) for value in tables[0]]
    specs = {
        "000001.SH": ("sh", "上证指数", "sh000001"),
        "399001.SZ": ("sz", "深证成指", "sz399001"),
        "399006.SZ": ("cyb", "创业板指", "sz399006"),
        "000688.SH": ("kc50", "科创50", "sh000688"),
        "000300.SH": ("hs300", "沪深300", "sh000300"),
        "000905.SH": ("zz500", "中证500", "sh000905"),
    }
    indices: dict[str, dict[str, Any]] = {}
    rises = falls = 0
    for values in tables[1:]:
        row = dict(zip(headers, values))
        symbol = str(row.get("证券代码", ""))
        if symbol not in specs:
            continue
        key_name, display_name, instrument_id = specs[symbol]
        try:
            price = float(row.get("最新价") or 0)
            change = float(row.get("涨跌幅") or 0)
        except (TypeError, ValueError):
            price = change = 0.0
        indices[key_name] = {
            "code": symbol.split(".", 1)[0],
            "name": str(row.get("证券简称") or display_name),
            "price": price,
            "change_pct": change,
            "instrument_id": instrument_id,
            "data_source": "ifind_mcp",
        }
        if symbol in ("000001.SH", "399001.SZ"):
            try:
                rises += int(float(row.get("上涨家数") or 0))
                falls += int(float(row.get("下跌家数") or 0))
            except (TypeError, ValueError):
                pass
    if not indices:
        return {}
    result = {
        "indices": indices,
        "market_breadth": {"advancers": rises, "decliners": falls, "unchanged": 0},
        "data_source": "ifind_mcp",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    _cache.set(key, dict(result))
    return result


def status() -> dict[str, Any]:
    return {
        "enabled": config.IFIND_MCP_ENABLED,
        "configured": bool(
            config.IFIND_MCP_AUTH_TOKEN
            and config.IFIND_MCP_STOCK_URL
            and config.IFIND_MCP_NEWS_URL
            and config.IFIND_MCP_INDEX_URL
        ),
        "last_error": _last_error,
        "cache": _cache.stats(),
    }
