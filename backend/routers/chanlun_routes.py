from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, HTTPException, Query, Request

from ai.analysis_agent import SYSTEM_PROMPT, build_analysis_prompt, parse_llm_response
from ai.divergence import DivergenceDetector
from ai.llm_client import get_llm_client
from ai.strategy_engine import StrategyEngine
from ai.wave_classifier import WaveClassifier
from chanlun.elements import ChanlunAnalysis
from core.chanlun_analysis import (
    DEFAULT_KLINE_LIMIT,
    chanlun_cache_key,
    get_kline_df_for_ai,
    run_analysis,
)
from core.chanlun_response import serialize_chanlun_analysis
from deps import check_chanlun_rate_limits, client_ip
from utils import ai_signal_llm_cache, ai_signal_rule_cache, chanlun_cache, chanlun_multi_cache

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/api/chanlun/{code}", tags=["缠论"], summary="缠论完整分析")
async def analyze_chanlun(
    request: Request,
    code: str,
    level: str = Query(
        "daily",
        pattern="^(1min|5min|15min|30min|60min|daily|weekly|monthly)$",
    ),
    limit: int = Query(DEFAULT_KLINE_LIMIT, ge=20, le=5000),
    start_date: str | None = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
):
    check_chanlun_rate_limits(client_ip(request))
    result = await asyncio.to_thread(
        run_analysis,
        code,
        level,
        kline_limit=limit,
        start_date=start_date,
        end_date=end_date,
    )
    return serialize_chanlun_analysis(result)


@router.get("/api/chanlun/{code}/multi-level", tags=["缠论"], summary="多级别并行缠论分析")
async def chanlun_multi_level(
    request: Request,
    code: str,
    levels: str = Query(
        "daily,weekly,30min",
        description="逗号分隔的分析级别，如 daily,weekly,30min",
    ),
):
    level_list = [l.strip() for l in levels.split(",") if l.strip()]
    level_list = list(dict.fromkeys(level_list))
    check_chanlun_rate_limits(client_ip(request), tokens=min(len(level_list), 4))

    cache_key = f"multi:{code}:{','.join(level_list)}"
    cached = chanlun_multi_cache.get(cache_key)
    if cached is not None:
        return cached

    t0 = time.time()

    def _serialize_result(result: ChanlunAnalysis) -> dict:
        return {
            "level": result.level,
            "trend": result.trend,
            "summary": result.summary,
            "bis_count": len(result.bis),
            "zhongshus_count": len(result.zhongshus),
            "signals_count": len(result.signals),
            "signals": [
                {
                    "type": s.type,
                    "price": s.price,
                    "datetime": str(s.datetime)[:19],
                    "confidence": s.confidence,
                    "description": s.description,
                }
                for s in result.signals[-3:]
            ],
            "supportResistance": [
                {
                    "type": lvl.type,
                    "price": lvl.price,
                    "datetime": str(lvl.datetime)[:19],
                    "strength": lvl.strength,
                }
                for lvl in result.support_resistance[-5:]
            ],
        }

    results: dict[str, dict | str] = {}

    def _safe_analyze(level: str) -> tuple[str, dict | str]:
        try:
            result = run_analysis(code, level, kline_limit=DEFAULT_KLINE_LIMIT)
            return level, _serialize_result(result)
        except HTTPException:
            return level, "数据不足"
        except Exception:
            log.debug("多级别缠论分析失败 code=%s level=%s", code, level, exc_info=True)
            return level, "数据不足"

    def _run_pool():
        with ThreadPoolExecutor(max_workers=min(len(level_list), 4)) as pool:
            futures = {pool.submit(_safe_analyze, lv): lv for lv in level_list}
            for future in as_completed(futures):
                lv, data = future.result(timeout=60)
                results[lv] = data

    await asyncio.to_thread(_run_pool)

    ordered = {lv: results.get(lv, "未知错误") for lv in level_list}
    t1 = time.time()
    payload = {
        "code": code,
        "levels": ordered,
        "count": len(level_list),
        "elapsed_ms": round((t1 - t0) * 1000, 1),
    }
    chanlun_multi_cache.set(cache_key, payload)
    return payload


def _ai_signal_cache_key(code: str, level: str, model: str, use_llm: bool) -> str:
    return f"ai:{code}:{level}:{model}:{'llm' if use_llm else 'rule'}"


def _apply_counter_trend_guard(
    payload: dict,
    *,
    trend: str,
    divergence: dict | None,
    resonance: dict | None,
    signals: list,
) -> dict:
    """低证据逆势背驰只能作为反弹/回调观察，不能直接升级为交易建议。"""
    guarded = dict(payload)
    default_guard = {
        "applied": False,
        "mode": None,
        "original_direction": payload.get("direction"),
        "reason": None,
    }
    if not divergence:
        guarded["decision_guard"] = default_guard
        return guarded

    grade = divergence.get("evidence_grade")
    chan_type = divergence.get("chan_type")
    weak_structure = grade == "C" and chan_type in {"consolidation", "momentum"}
    oscillator_confirmed = bool(
        divergence.get("rsi_confirm") or divergence.get("kdj_confirm")
    )
    trend_rows = (resonance or {}).get("trends") or []
    down_count = sum(1 for item in trend_rows if item.get("trend") == "下跌")
    up_count = sum(1 for item in trend_rows if item.get("trend") == "上涨")
    bearish_background = trend == "下跌" and (
        down_count >= 2 or (resonance or {}).get("direction") == "卖出"
    )
    bullish_background = trend == "上涨" and (
        up_count >= 2 or (resonance or {}).get("direction") == "买入"
    )

    div_time = str(divergence.get("datetime") or "")

    def has_point(point_type: str) -> bool:
        for signal in signals:
            signal_type = signal.get("type") if isinstance(signal, dict) else signal.type
            signal_time = signal.get("datetime") if isinstance(signal, dict) else signal.datetime
            if signal_type == point_type and (not div_time or str(signal_time) >= div_time):
                return True
        return False

    direction = payload.get("direction")
    bottom_counter = (
        direction == "买入"
        and divergence.get("type") == "bottom"
        and bearish_background
        and not has_point("三买")
    )
    top_counter = (
        direction == "卖出"
        and divergence.get("type") == "top"
        and bullish_background
        and not has_point("三卖")
    )
    if not weak_structure or oscillator_confirmed or not (bottom_counter or top_counter):
        guarded["decision_guard"] = default_guard
        return guarded

    if bottom_counter:
        mode = "counter_trend_rebound"
        reason = "多级别仍下跌，当前仅C级盘整背驰/力度背离，降级为反弹观察；等待RSI/KDJ、趋势转强或三买确认"
    else:
        mode = "counter_trend_pullback"
        reason = "多级别仍上涨，当前仅C级盘整背驰/力度背离，降级为回调观察；等待RSI/KDJ、趋势转弱或三卖确认"

    guarded.update({
        "direction": "观望",
        "confidence": min(float(payload.get("confidence") or 0), 0.49),
        "risk_level": "高",
        "entry_price": None,
        "stop_loss": None,
        "take_profit": None,
        "holding_period": "等待当前级别确认",
        "description": reason,
        "decision_guard": {
            "applied": True,
            "mode": mode,
            "original_direction": direction,
            "reason": reason,
        },
    })
    return guarded


def build_ai_signal_response(code: str, level: str, model: str, use_llm: bool) -> dict:
    """规则策略 + 可选 LLM；供线程池与缓存复用。"""
    df_for_ai, result = get_kline_df_for_ai(code, level)
    current_price = float(result.klines[-1].close) if result.klines else 0.0

    classifier = WaveClassifier()
    wave_class = classifier.classify(result.xiangs, result.zhongshus, current_price)

    divergence = None
    divergences = []
    if not df_for_ai.empty:
        try:
            # 结构可能跨越 200 根以上 K 线，力度比较必须使用完整分析窗口。
            div_detector = DivergenceDetector(df_for_ai, analysis_level=level)
            bi_divergences = div_detector.check_divergences(
                result.bis,
                centers=result.bi_zhongshus,
                source_type="bi",
                structure_level=1,
                limit=10,
            )
            segment_divergences = div_detector.check_divergences(
                result.xiangs,
                centers=result.zhongshus,
                source_type="segment",
                structure_level=2,
                limit=10,
            )
            divergences = sorted(
                [*bi_divergences, *segment_divergences],
                key=lambda item: (item["datetime"], item["structure_level"]),
            )[-12:]
            divergence = div_detector.select_primary_divergence(divergences)
        except Exception:
            log.debug("背驰检测失败 code=%s", code, exc_info=True)

    engine = StrategyEngine(
        signals=result.signals,
        trend=wave_class["trend"],
        current_price=current_price,
        current_level=level,
        zhongshus=result.zhongshus,
        divergence=divergence,
    )
    signal = engine.generate_signal()
    signal.stock_code = code

    resonance = None
    if level == "30min":
        try:
            level_trends = [{"trend": wave_class["trend"], "level": level}]
            for higher_level in ("daily", "weekly"):
                higher_key = chanlun_cache_key(code, higher_level, DEFAULT_KLINE_LIMIT)
                higher_result = chanlun_cache.get(higher_key)
                if higher_result is None:
                    higher_result = run_analysis(
                        code, higher_level, kline_limit=DEFAULT_KLINE_LIMIT
                    )
                    chanlun_cache.set(higher_key, higher_result)
                if higher_result is None:
                    continue
                higher_cls = WaveClassifier().classify(
                    higher_result.xiangs,
                    higher_result.zhongshus,
                    float(higher_result.klines[-1].close) if higher_result.klines else 0.0,
                )
                level_trends.append({"trend": higher_cls["trend"], "level": higher_level})
            resonance = classifier.multi_level_resonance(level_trends)
            resonance["trends"] = level_trends
        except Exception:
            log.debug("多级别共振计算失败 code=%s", code, exc_info=True)

    llm_result = None
    llm_error = None
    if use_llm:
        try:
            llm = get_llm_client(model)
            prompt = build_analysis_prompt(
                code=code,
                level=level,
                klines=[k.__dict__ for k in result.klines],
                trend=wave_class["trend"],
                divergence=divergence,
                signals=[s.__dict__ for s in result.signals],
                zhongshus=[z.__dict__ for z in result.zhongshus],
                bis=[b.__dict__ for b in result.bis],
                resonance=resonance,
            )
            raw = llm.chat(prompt, system=SYSTEM_PROMPT, temperature=0.3)
            llm_result = parse_llm_response(raw)
            if not isinstance(llm_result, dict):
                llm_result = None
                llm_error = "LLM 解析结果非对象"
        except Exception as e:
            llm_error = str(e)
            log.warning("LLM 策略生成失败 code=%s model=%s: %s", code, model, e)

    lr = llm_result if isinstance(llm_result, dict) else None

    def llm_or_rule(key: str, rule_value):
        return lr[key] if lr is not None and key in lr else rule_value

    recommendation = {
        "stock_code": signal.stock_code,
        "level": signal.level,
        "direction": llm_or_rule("direction", signal.direction),
        "confidence": llm_or_rule("confidence", signal.confidence),
        "risk_level": llm_or_rule("risk_level", signal.risk_level),
        "entry_price": llm_or_rule("entry_price", signal.entry_price),
        "stop_loss": llm_or_rule("stop_loss", signal.stop_loss),
        "take_profit": llm_or_rule("take_profit", signal.take_profit),
        "holding_period": llm_or_rule("holding_period", signal.holding_period),
        "description": llm_or_rule("reasoning", signal.description),
        "trend": wave_class["trend"],
        "divergence": divergence,
        "divergences": divergences,
        "resonance": resonance,
        "llm": {
            "model": model,
            "used": lr is not None and llm_error is None,
            "error": llm_error,
            "skipped": not use_llm,
        },
    }
    return _apply_counter_trend_guard(
        recommendation,
        trend=wave_class["trend"],
        divergence=divergence,
        resonance=resonance,
        signals=result.signals,
    )


@router.get("/api/chanlun/{code}/ai", tags=["缠论"], summary="AI 策略信号（背驰 + 规则 + 可选 LLM）")
async def ai_signal(
    request: Request,
    code: str,
    level: str = Query("daily"),
    model: str = Query("deepseek", description="AI 模型：deepseek / gemini"),
    use_llm: bool = Query(
        False,
        description="为 true 时调用大模型增强；默认仅规则引擎，响应更快",
    ),
):
    check_chanlun_rate_limits(client_ip(request))

    cache_key = _ai_signal_cache_key(code, level, model, use_llm)
    cache = ai_signal_llm_cache if use_llm else ai_signal_rule_cache
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        payload = await asyncio.to_thread(build_ai_signal_response, code, level, model, use_llm)
        cache.set(cache_key, payload)
        return payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI 策略生成失败: {e!s}",
        ) from e
