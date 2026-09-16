"""缠论分析：K 线拉取 + 引擎（供路由与 AI 复用）。"""
from __future__ import annotations

import math
import pandas as pd
from fastapi import HTTPException

from chanlun.elements import ChanlunAnalysis
from chanlun.engine import ChanlunEngine
from core.kline_serialize import analysis_klines_to_df
from services.market_data_service import get_kline_hist  # used by run_analysis
from utils import chanlun_cache, chanlun_multi_cache

DEFAULT_KLINE_LIMIT = 500
SCREENING_KLINE_LIMIT = 200
MAX_INTRADAY_KLINE_LIMIT = 5000


def chanlun_cache_key(
    code: str,
    level: str,
    kline_limit: int = DEFAULT_KLINE_LIMIT,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """缓存键含窗口与日期范围，避免不同历史区间复用最近行情。"""
    return f"{code}:{level}:{kline_limit}:{start_date or '-'}:{end_date or '-'}"


def level_to_period(level: str) -> str:
    mapping = {
        # 当前 fallback 分钟源只稳定提供 5/15/30/60 分钟历史；1 分钟在
        # iFinD 可用时会由其原生返回，legacy 则兼容到 5 分钟，避免空图。
        "1min": "5",
        "5min": "5",
        "15min": "15",
        "30min": "30",
        "60min": "60",
        "daily": "daily",
        "weekly": "weekly",
        "monthly": "monthly",
    }
    return mapping.get(level, "daily")


def resolve_kline_limit(
    level: str,
    start_date: str | None = None,
    end_date: str | None = None,
    default_limit: int = DEFAULT_KLINE_LIMIT,
) -> int:
    """按用户选定日期范围估算分钟 K 线数量，避免默认 500 根截断历史。"""
    period = level_to_period(level)
    if not start_date:
        return default_limit
    start = pd.to_datetime(start_date, errors="coerce")
    end = pd.to_datetime(end_date, errors="coerce") if end_date else pd.Timestamp.now()
    if pd.isna(start) or pd.isna(end) or end < start:
        return default_limit
    days = max(1, (end.normalize() - start.normalize()).days)
    if period.isdigit():
        bars_per_day = {"1": 240, "5": 48, "15": 16, "30": 8, "60": 4}.get(period, 8)
        estimated = math.ceil((days * 5 / 7 + 1) * bars_per_day) + bars_per_day * 5
        maximum = MAX_INTRADAY_KLINE_LIMIT
    elif period == "daily":
        estimated = math.ceil(days * 5 / 7) + 10
        maximum = 2000
    elif period == "weekly":
        estimated = math.ceil(days / 7) + 4
        maximum = 2000
    else:
        estimated = math.ceil(days / 30) + 3
        maximum = 2000
    return min(maximum, max(default_limit, estimated))


def run_analysis(
    code: str,
    level: str,
    kline_limit: int = DEFAULT_KLINE_LIMIT,
    start_date: str | None = None,
    end_date: str | None = None,
) -> ChanlunAnalysis:
    kline_limit = resolve_kline_limit(level, start_date, end_date, kline_limit)
    cache_key = chanlun_cache_key(code, level, kline_limit, start_date, end_date)
    cached = chanlun_cache.get(cache_key)
    if cached is not None:
        return cached

    period = level_to_period(level)
    df = get_kline_hist(
        code,
        period=period,
        start_date=start_date,
        end_date=end_date,
        adjust="qfq",
        limit=kline_limit,
    )

    if df.empty or len(df) < 20:
        raise HTTPException(
            status_code=404,
            detail=f"{code} {level}级别K线数据不足（仅{len(df) if not df.empty else 0}根），请换日线/30分钟级别尝试",
        )

    if len(df) > kline_limit:
        df = df.tail(kline_limit).reset_index(drop=True)

    engine = ChanlunEngine(df)
    result = engine.analyze(level=level)
    result.stock_code = code

    chanlun_cache.set(cache_key, result)
    chanlun_multi_cache.delete_prefix(f"multi:{code}:")
    return result


def get_kline_df_for_ai(
    code: str, level: str, kline_limit: int = DEFAULT_KLINE_LIMIT
) -> tuple[pd.DataFrame, ChanlunAnalysis]:
    result = run_analysis(code, level, kline_limit=kline_limit)
    return analysis_klines_to_df(result.klines), result
