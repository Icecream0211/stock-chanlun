"""缠论分析 API 响应序列化。"""
from __future__ import annotations

from chanlun.elements import ChanlunAnalysis
from core.chanlun_analysis import level_to_period


def _serialize_zhongshu(z) -> dict:
    return {
        "id": z.id,
        "start": str(z.start)[:19],
        "end": str(z.end)[:19],
        "range_high": z.range_high,
        "range_low": z.range_low,
        "zg": z.zg if z.zg is not None else z.range_high,
        "zd": z.zd if z.zd is not None else z.range_low,
        "gg": z.gg if z.gg is not None else z.range_high,
        "dd": z.dd if z.dd is not None else z.range_low,
        "level": z.level,
        "confirmed": z.confirmed,
        "source_type": z.source_type,
        "status": z.status,
        "structure_count": z.structure_count,
        "extension_count": z.extension_count,
        "exit_direction": z.exit_direction,
        "expansion_type": z.expansion_type,
        "parent_id": z.parent_id,
        "child_ids": z.child_ids,
    }


def serialize_chanlun_analysis(result: ChanlunAnalysis) -> dict:
    """将 ChanlunAnalysis 转为前端 JSON（含 K 线，减少单独 /kline 请求）。"""
    klines = [
        {
            "date": str(k.date)[:19],
            "open": k.open,
            "high": k.high,
            "low": k.low,
            "close": k.close,
            "volume": k.volume,
        }
        for k in result.klines
    ]
    period = level_to_period(result.level)
    data_period_note = (
        "5min"
        if result.level == "1min"
        else period
    )
    return {
        "stock_code": result.stock_code,
        "level": result.level,
        "data_period": data_period_note,
        "trend": result.trend,
        "summary": result.summary,
        "klines": klines,
        "total": len(klines),
        "inclusions": [
            {
                "start": str(item.start)[:19],
                "end": str(item.end)[:19],
                "merged_date": str(item.merged_date)[:19],
                "direction": item.direction,
                "count": item.count,
                "high": item.high,
                "low": item.low,
                "high_date": str(item.high_date)[:19],
                "low_date": str(item.low_date)[:19],
            }
            for item in result.inclusions
        ],
        "bis": [
            {
                "id": b.id,
                "start": str(b.start)[:19],
                "end": str(b.end)[:19],
                "direction": b.direction,
                "high": b.high,
                "low": b.low,
                "start_price": b.start_price,
                "end_price": b.end_price,
                "confirmed": b.confirmed,
                "rule": b.rule,
            }
            for b in result.bis
        ],
        "xiangs": [
            {
                "id": s.id,
                "start": str(s.start)[:19],
                "end": str(s.end)[:19],
                "direction": s.direction,
                "high": s.high,
                "low": s.low,
                "start_price": s.start_price,
                "end_price": s.end_price,
                "confirmed": s.confirmed,
            }
            for s in result.xiangs
        ],
        "zhongshus": [_serialize_zhongshu(z) for z in result.zhongshus],
        "bi_zhongshus": [_serialize_zhongshu(z) for z in result.bi_zhongshus],
        "signals": [
            {
                "type": s.type,
                "level": s.level,
                "price": s.price,
                "datetime": str(s.datetime)[:19],
                "confidence": s.confidence,
                "stop_loss": s.stop_loss,
                "take_profit": s.take_profit,
                "description": s.description,
            }
            for s in result.signals
        ],
        "supportResistance": [
            {
                "type": lvl.type,
                "price": lvl.price,
                "source": lvl.source,
                "relatedId": lvl.related_id,
                "datetime": str(lvl.datetime)[:19],
                "strength": lvl.strength,
            }
            for lvl in result.support_resistance
        ],
    }
