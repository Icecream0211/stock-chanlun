"""A 股统一行情入口：按配置顺序选择 iFinD 或现有腾讯/新浪实现。"""
from __future__ import annotations

import logging

import pandas as pd

import config
from services.akshare_service import (
    get_kline_hist as get_legacy_kline_hist,
    get_realtime_quote as get_legacy_realtime_quote,
)
from services.ifind_service import get_ifind_kline, get_ifind_realtime_quote, ifind_status
from services.ifind_mcp_service import status as ifind_mcp_status

log = logging.getLogger(__name__)


def _sources() -> tuple[str, ...]:
    aliases = {"tencent": "legacy", "sina": "legacy", "akshare": "legacy"}
    result: list[str] = []
    for source in config.MARKET_DATA_SOURCES:
        canonical = aliases.get(source, source)
        if canonical in ("ifind", "legacy") and canonical not in result:
            result.append(canonical)
    return tuple(result) or ("legacy",)


def get_kline_hist(
    code: str,
    period: str = "daily",
    start_date: str | None = None,
    end_date: str | None = None,
    adjust: str = "qfq",
    limit: int = 500,
) -> pd.DataFrame:
    for source in _sources():
        if source == "ifind":
            if not config.IFIND_ENABLED:
                continue
            frame = get_ifind_kline(code, period, start_date, end_date, adjust, limit)
        else:
            frame = get_legacy_kline_hist(code, period, start_date, end_date, adjust, limit)
        if not frame.empty:
            frame.attrs["data_source"] = source
            return frame
        log.debug("行情源未返回 K 线 source=%s code=%s period=%s", source, code, period)
    return pd.DataFrame()


def _missing(value: object) -> bool:
    if value is None or value == "":
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _merge_quotes(primary: pd.DataFrame, fallback: pd.DataFrame) -> pd.DataFrame:
    if primary.empty:
        return fallback.copy()
    if fallback.empty:
        return primary.copy()
    columns = ["代码", "名称", "最新价", "涨跌幅", "成交量", "成交额", "今开", "最高", "最低", "昨收"]
    fallback_rows = {str(row.get("代码", "")).zfill(6): row for _, row in fallback.iterrows()}
    records: list[dict] = []
    seen: set[str] = set()
    for _, row in primary.iterrows():
        record = row.to_dict()
        code = str(record.get("代码", "")).zfill(6)
        seen.add(code)
        supplement = fallback_rows.get(code)
        change_missing = _missing(record.get("涨跌幅"))
        if supplement is not None:
            for column in columns:
                if column not in record or _missing(record.get(column)):
                    record[column] = supplement.get(column)
        if change_missing and not _missing(record.get("昨收")):
            previous = float(record["昨收"])
            if previous:
                record["涨跌幅"] = round((float(record["最新价"]) - previous) / previous * 100, 2)
        records.append(record)
    for code, row in fallback_rows.items():
        if code not in seen:
            records.append(row.to_dict())
    return pd.DataFrame(records).reindex(columns=columns)


def get_realtime_quote(codes: list[str]) -> pd.DataFrame:
    primary = pd.DataFrame()
    used_sources: list[str] = []
    for source in _sources():
        if source == "ifind":
            if not config.IFIND_ENABLED:
                continue
            frame = get_ifind_realtime_quote(codes)
        else:
            # iFinD 的实时通用指标不含证券简称和昨收；现有源同时负责补齐字段和缺失代码。
            frame = get_legacy_realtime_quote(codes)
        if frame.empty:
            continue
        if primary.empty:
            primary = frame.copy()
        else:
            primary = _merge_quotes(primary, frame)
        used_sources.append(source)
        if source == "legacy" or len(primary) >= len(set(codes)):
            # iFinD 优先时仍继续到 legacy 补齐名称/昨收；legacy 优先时无需重复请求。
            if source == "legacy" or all(
                not _missing(row.get("名称")) and not _missing(row.get("昨收"))
                for _, row in primary.iterrows()
            ):
                break
    if not primary.empty:
        primary.attrs["data_source"] = "+".join(used_sources)
    return primary


def market_data_status() -> dict:
    return {
        "priority": list(_sources()),
        "active_candidates": [
            source for source in _sources() if source != "ifind" or config.IFIND_ENABLED
        ],
        "ifind": ifind_status(),
        "ifind_mcp_fallback": ifind_mcp_status(),
        "legacy": {"enabled": "legacy" in _sources(), "providers": ["tencent", "sina"]},
    }
