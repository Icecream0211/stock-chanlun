"""缠论背驰/盘整背驰与指标力度背离检测。

这里刻意把三个概念分开：
- 趋势背驰：至少两个同级、不重叠且同向推进的中枢，末段创新高/低但力度减弱；
- 盘整背驰：围绕单个中枢的第一、第三同向段比较，后段创新高/低但力度减弱；
- 力度背离：只有价格与 MACD/RSI/KDJ 条件，结构条件尚不成立。

MACD/RSI/KDJ 都是力度证据，不是缠论背驰的结构定义。
"""
import pandas as pd
import numpy as np
from typing import Literal, Optional

from chanlun.elements import Bi, XiangSegment, Zhongshu


# MACD：后一段面积低于前一段该比例以下视为力度显著减弱
MACD_WEAKEN_RATIO = 0.85
MACD_AREA_EPS = 1e-15
PRICE_EPS = 1e-12
MIN_STRUCTURES_FOR_DIV = 3
# 旧常量保留给外部调用兼容。
MIN_BIS_FOR_DIV = MIN_STRUCTURES_FOR_DIV
# 每段至少若干根 K 线才参与力度对比，避免单子线噪声
MIN_BARS_PER_SEGMENT = 2
# MACD 已满足背驰时，RSI 或 KDJ(J) 同向背离各小幅抬高概率上限
OSC_CONFIRM_BOOST = 0.07

Structure = Bi | XiangSegment
ChanDivergenceType = Literal["trend", "consolidation", "momentum"]
StructureType = Literal["bi", "segment"]

LEVEL_LABELS = {
    "1min": "1分钟",
    "5min": "5分钟",
    "15min": "15分钟",
    "30min": "30分钟",
    "60min": "60分钟",
    "daily": "日K",
    "weekly": "周K",
    "monthly": "月K",
}

CHAN_TYPE_LABELS: dict[ChanDivergenceType, str] = {
    "trend": "趋势背驰",
    "consolidation": "盘整背驰",
    "momentum": "力度背离",
}

# 该百分比表示“当前结果与检测规则的匹配程度”，不是未来涨跌成功率。
# 证据越少、结构越弱，上限越低，避免单一 MACD 因面积大幅衰减而显示 100%。
MATCH_SCORE_CAPS: dict[ChanDivergenceType, dict[str, float]] = {
    "momentum": {"C": 0.55, "B": 0.68, "A": 0.78},
    "consolidation": {"C": 0.65, "B": 0.78, "A": 0.88},
    "trend": {"C": 0.72, "B": 0.85, "A": 0.93},
}


def calculate_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """计算 MACD 指标，返回追加 dif/dea/bar 列的 DataFrame。"""
    from core.indicators import calculate_macd_df

    return calculate_macd_df(df, fast=fast, slow=slow, signal=signal)


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """计算 RSI（Wilder 平滑，与常见行情软件一致）"""
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def calculate_kdj(
    df: pd.DataFrame,
    n: int = 9,
    m1: int = 3,
    m2: int = 3
) -> pd.DataFrame:
    """计算 KDJ 指标"""
    df = df.copy()
    low_n = df['low'].rolling(n, min_periods=1).min()
    high_n = df['high'].rolling(n, min_periods=1).max()
    rsv = (df['close'] - low_n) / (high_n - low_n + 1e-9) * 100
    df['K'] = rsv.ewm(com=m1 - 1, adjust=False).mean()
    df['D'] = df['K'].ewm(com=m2 - 1, adjust=False).mean()
    df['J'] = 3 * df['K'] - 2 * df['D']
    return df


def money(v: float) -> float:
    """格式化金额显示"""
    return round(v, 2)


def macd_area(bars: pd.Series) -> float:
    """计算 MACD 柱全绝对值面积（近似积分），忽略 NaN"""
    arr = bars.to_numpy(dtype=float)
    return float(np.nansum(np.abs(arr)))


def macd_area_directional(bars: pd.Series, seg_type: str) -> float:
    """
    与走势同向的 MACD 柱累计面积（忽略反向柱），更符合「上涨笔比红柱、下跌笔比绿柱」的习惯。
    top（向上笔顶背驰）：累计 bar > 0 部分；bottom（向下笔底背驰）：累计 bar < 0 的绝对值。
    """
    arr = bars.to_numpy(dtype=float)
    if seg_type == "top":
        return float(np.nansum(np.maximum(arr, 0.0)))
    if seg_type == "bottom":
        return float(np.nansum(np.abs(np.minimum(arr, 0.0))))
    raise ValueError(f"seg_type must be 'top' or 'bottom', got {seg_type!r}")


def _nan_extreme(series: pd.Series, *, high_extreme: bool) -> float:
    """段内 RSI/KDJ 极值；无有效数据时返回 nan"""
    a = series.to_numpy(dtype=float)
    if high_extreme:
        return float(np.nanmax(a))
    return float(np.nanmin(a))


class DivergenceDetector:
    """
    分两层检测：
    1. 价格创新高/低 + MACD 同向柱面积减弱，RSI/KDJ 仅作追加证据；
    2. 结合相同来源、相同结构级别的中枢，分类为趋势背驰、盘整背驰或力度背离。
    """

    def __init__(self, df: pd.DataFrame, analysis_level: str = ""):
        self.df = df.copy()
        self.analysis_level = analysis_level
        self.df = calculate_macd(self.df)
        self.df['rsi'] = calculate_rsi(self.df)
        self.df = calculate_kdj(self.df)
        self.df.reset_index(drop=True, inplace=True)

    def check_divergence(
        self,
        structures: list[Structure],
        *,
        centers: Optional[list[Zhongshu]] = None,
        source_type: StructureType = "bi",
        structure_level: int = 1,
    ) -> Optional[dict]:
        """
        检测背驰: 比较最近两个同向段的力度
        返回: type、probability、macd_ratio、price_drop|price_rise、description，
        以及 rsi_confirm / kdj_confirm（是否与 MACD 背驰同向的振荡器背离）。
        顶、底同时满足时取概率更高者；概率相同则取第二段结束时间更晚者。
        """
        results = self.check_divergences(
            structures,
            centers=centers,
            source_type=source_type,
            structure_level=structure_level,
            limit=20,
        )
        return self.select_primary_divergence(results)

    def check_divergences(
        self,
        structures: list[Structure],
        *,
        centers: Optional[list[Zhongshu]] = None,
        source_type: StructureType = "bi",
        structure_level: int = 1,
        limit: int = 8,
    ) -> list[dict]:
        """扫描确认结构，返回带结构语义、可在图上定位的多处结果。"""
        confirmed = [s for s in structures if getattr(s, "confirmed", True)]
        if len(confirmed) < MIN_STRUCTURES_FOR_DIV:
            return []

        usable_centers = self._base_centers(
            centers or [], source_type=source_type, structure_level=structure_level
        )
        results: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for direction, seg_type in (("up", "top"), ("down", "bottom")):
            directional = [s for s in confirmed if s.direction == direction]
            pairs = list(zip(directional, directional[1:]))
            structural_pair = self._trend_comparison_pair(
                confirmed, usable_centers, direction
            )
            if structural_pair is not None:
                pairs.append(structural_pair)

            for previous, current in pairs:
                pair_key = (str(previous.id), str(current.id), seg_type)
                if pair_key in seen:
                    continue
                seen.add(pair_key)
                chan_type, related_centers = self._classify_chan_type(
                    previous,
                    current,
                    seg_type,
                    usable_centers,
                )
                result = self._check_segment_divergence(
                    previous,
                    current,
                    seg_type,
                    chan_type=chan_type,
                    related_centers=related_centers,
                    source_type=source_type,
                    structure_level=structure_level,
                )
                if result:
                    results.append(result)

        # 同一端点若同时出现低层级与高层级结果，全部保留，供图上区分。
        results.sort(key=lambda item: (item["datetime"], item["structure_level"]))
        return results[-max(1, int(limit)):]

    @staticmethod
    def select_primary_divergence(results: list[dict]) -> Optional[dict]:
        """主信号先取最近端点；同端点优先标准结构与更高结构层级。"""
        if not results:
            return None
        type_rank = {"trend": 2, "consolidation": 1, "momentum": 0}
        return max(
            results,
            key=lambda item: (
                item.get("datetime"),
                type_rank.get(item.get("chan_type"), 0),
                int(item.get("structure_level", 0)),
                float(item.get("probability", 0)),
            ),
        )

    @staticmethod
    def _base_centers(
        centers: list[Zhongshu],
        *,
        source_type: StructureType,
        structure_level: int,
    ) -> list[Zhongshu]:
        """只取与待比较结构同源、同级的基础中枢，扩张父中枢不能混作同级趋势中枢。"""
        return sorted(
            [
                z for z in centers
                if z.source_type == source_type
                and z.level == structure_level
                and z.status != "expanded"
                and z.confirmed
            ],
            key=lambda z: (z.start, z.end),
        )

    @staticmethod
    def _center_trend_direction(centers: list[Zhongshu]) -> Optional[str]:
        """同级中枢必须至少两个且区间互不重叠、同向推进，才构成趋势上下文。"""
        if len(centers) < 2:
            return None
        pairs = list(zip(centers, centers[1:]))
        if all(right.range_low > left.range_high for left, right in pairs):
            return "up"
        if all(right.range_high < left.range_low for left, right in pairs):
            return "down"
        return None

    @classmethod
    def _trend_comparison_pair(
        cls,
        structures: list[Structure],
        centers: list[Zhongshu],
        direction: str,
    ) -> Optional[tuple[Structure, Structure]]:
        """取最后中枢前的同向进入段与中枢后的同向离开段，近似 b/B/c 力度比较。"""
        if cls._center_trend_direction(centers) != direction:
            return None
        last = centers[-1]
        if last.status != "completed" or last.exit_direction != direction:
            return None
        incoming = [
            s for s in structures
            if s.direction == direction and s.end <= last.start
        ]
        outgoing = [
            s for s in structures
            if s.direction == direction and s.start >= last.end
        ]
        if not incoming or not outgoing:
            return None
        return incoming[-1], outgoing[-1]

    @classmethod
    def _classify_chan_type(
        cls,
        seg1: Structure,
        seg2: Structure,
        seg_type: str,
        centers: list[Zhongshu],
    ) -> tuple[ChanDivergenceType, list[Zhongshu]]:
        """按中枢结构分类；结构证据不足时必须降级为力度背离。"""
        containing = [
            z for z in centers
            if seg1.id in z.xiang_ids and seg2.id in z.xiang_ids
        ]
        if containing:
            # 单个中枢内第一、第三同向结构的力度比较属于盘整背驰。
            return "consolidation", containing[-1:]

        direction = "up" if seg_type == "top" else "down"
        trend_direction = cls._center_trend_direction(centers)
        if trend_direction == direction and centers:
            last = centers[-1]
            if (
                last.status == "completed"
                and last.exit_direction == direction
                and seg1.end <= last.start
                and seg2.start >= last.end
            ):
                return "trend", centers
        return "momentum", []

    def _rsi_confirms(self, seg_type: str, s1_df: pd.DataFrame, s2_df: pd.DataFrame) -> bool:
        """顶: 价新高但段内 RSI 高点不及前一段；底: 价新低但 RSI 低点抬高"""
        if "rsi" not in s1_df.columns:
            return False
        if seg_type == "top":
            r1 = _nan_extreme(s1_df["rsi"], high_extreme=True)
            r2 = _nan_extreme(s2_df["rsi"], high_extreme=True)
            if np.isnan(r1) or np.isnan(r2):
                return False
            return r2 < r1
        r1 = _nan_extreme(s1_df["rsi"], high_extreme=False)
        r2 = _nan_extreme(s2_df["rsi"], high_extreme=False)
        if np.isnan(r1) or np.isnan(r2):
            return False
        return r2 > r1

    def _kdj_j_confirms(self, seg_type: str, s1_df: pd.DataFrame, s2_df: pd.DataFrame) -> bool:
        """以 J 线为快速振荡器，逻辑同 RSI"""
        if "J" not in s1_df.columns:
            return False
        if seg_type == "top":
            j1 = _nan_extreme(s1_df["J"], high_extreme=True)
            j2 = _nan_extreme(s2_df["J"], high_extreme=True)
            if np.isnan(j1) or np.isnan(j2):
                return False
            return j2 < j1
        j1 = _nan_extreme(s1_df["J"], high_extreme=False)
        j2 = _nan_extreme(s2_df["J"], high_extreme=False)
        if np.isnan(j1) or np.isnan(j2):
            return False
        return j2 > j1

    def _check_segment_divergence(
        self,
        seg1: Structure,
        seg2: Structure,
        seg_type: str,
        *,
        chan_type: ChanDivergenceType = "momentum",
        related_centers: Optional[list[Zhongshu]] = None,
        source_type: StructureType = "bi",
        structure_level: int = 1,
    ) -> Optional[dict]:
        """比较两段的力度差异"""
        s1_df = self._get_segment_df(seg1.start, seg1.end)
        s2_df = self._get_segment_df(seg2.start, seg2.end)

        if (
            len(s1_df) < MIN_BARS_PER_SEGMENT
            or len(s2_df) < MIN_BARS_PER_SEGMENT
        ):
            return None

        d1 = macd_area_directional(s1_df["bar"], seg_type)
        d2 = macd_area_directional(s2_df["bar"], seg_type)
        if d1 > MACD_AREA_EPS and d2 > MACD_AREA_EPS:
            macd1, macd2 = d1, d2
            macd_force_kind = "directional"
        else:
            macd1 = macd_area(s1_df["bar"])
            macd2 = macd_area(s2_df["bar"])
            macd_force_kind = "abs"
        if macd1 <= MACD_AREA_EPS:
            return None

        threshold = macd1 * MACD_WEAKEN_RATIO

        if seg_type == "bottom":
            price1 = float(seg1.low)
            price2 = float(seg2.low)
            if price1 <= PRICE_EPS:
                return None
            if not (price2 < price1 and macd2 < threshold):
                return None
            change_key = "price_drop"
            desc_prefix = "价格新低"
        else:
            price1 = float(seg1.high)
            price2 = float(seg2.high)
            if price1 <= PRICE_EPS:
                return None
            if not (price2 > price1 and macd2 < threshold):
                return None
            change_key = "price_rise"
            desc_prefix = "价格新高"

        ratio = macd2 / macd1
        prob = min(1.0, (1 - ratio) + 0.5)

        rsi_ok = self._rsi_confirms(seg_type, s1_df, s2_df)
        kdj_ok = self._kdj_j_confirms(seg_type, s1_df, s2_df)
        if rsi_ok:
            prob = min(1.0, prob + OSC_CONFIRM_BOOST)
        if kdj_ok:
            prob = min(1.0, prob + OSC_CONFIRM_BOOST)

        tags: list[str] = []
        if rsi_ok:
            tags.append("RSI背离")
        if kdj_ok:
            tags.append("KDJ背离")
        extra_txt = f"，{'/'.join(tags)}共振" if tags else ""

        delta = abs(price2 - price1)
        pct_move = round(delta / price1, 3)
        confirmations = ["MACD"]
        if rsi_ok:
            confirmations.append("RSI")
        if kdj_ok:
            confirmations.append("KDJ")

        evidence_grade = {1: "C", 2: "B", 3: "A"}.get(len(confirmations), "C")
        raw_strength_score = round(prob, 2)
        match_score = round(
            min(prob, MATCH_SCORE_CAPS[chan_type][evidence_grade]), 2
        )
        structure_cn = "笔" if source_type == "bi" else "线段"
        level_cn = LEVEL_LABELS.get(self.analysis_level, self.analysis_level or "当前周期")
        chan_label = CHAN_TYPE_LABELS[chan_type]
        direction_cn = "顶" if seg_type == "top" else "底"
        strict_chan = chan_type != "momentum"
        center_ids = [z.id for z in (related_centers or [])]
        if chan_type == "trend":
            theory_note = "同级趋势至少两个同级中枢，末段创新高/低且力度衰竭"
            turn_scope = "同级趋势转折候选；结果可能为末中枢扩展、更高级盘整或反趋势"
        elif chan_type == "consolidation":
            theory_note = "围绕单个中枢比较第一、第三同向段的力度"
            turn_scope = "离开中枢力度不足，通常关注回到中枢；不等同趋势反转"
        else:
            theory_note = "仅满足价格与指标力度条件，尚无足够中枢结构证据"
            turn_scope = "辅助预警，不属于标准趋势背驰或盘整背驰"

        return {
            "type": seg_type,
            "orientation": seg_type,
            "chan_type": chan_type,
            "chan_type_label": chan_label,
            "strict_chan": strict_chan,
            "analysis_level": self.analysis_level,
            "structure_type": source_type,
            "structure_level": structure_level,
            "level_label": f"{level_cn}·{structure_cn}级",
            "level_meaning": "图表周期与递归结构层级，不代表信号强弱",
            "evidence_grade": evidence_grade,
            "evidence_label": f"{len(confirmations)}因子确认",
            "evidence_meaning": "工程证据等级 A/B/C，不是缠论走势级别",
            "score_meaning": "结构与力度规则匹配度，不代表未来涨跌成功率",
            "related_center_ids": center_ids,
            "center_count": len(center_ids),
            "theory_note": theory_note,
            "turn_scope": turn_scope,
            "large_turn_status": "not_evaluated",
            "large_turn_note": "若推断小背驰引发大转折，仍须更大级别末个次级中枢的三买/三卖确认",
            "probability": match_score,
            "match_score": match_score,
            "raw_strength_score": raw_strength_score,
            change_key: pct_move,
            "macd_ratio": round(ratio, 2),
            "macd_force": macd_force_kind,
            "rsi_confirm": rsi_ok,
            "kdj_confirm": kdj_ok,
            "confirmations": confirmations,
            "confirm_count": len(confirmations),
            "is_multi": len(confirmations) >= 2,
            "datetime": seg2.end,
            "price": price2,
            "start": seg2.start,
            "end": seg2.end,
            "previous_datetime": seg1.end,
            "previous_price": price1,
            "previous_structure_id": seg1.id,
            "current_structure_id": seg2.id,
            # 旧字段保留，避免已有前端/调用方中断。
            "previous_bi_id": seg1.id if source_type == "bi" else None,
            "current_bi_id": seg2.id if source_type == "bi" else None,
            "macd_area_previous": round(macd1, 6),
            "macd_area_current": round(macd2, 6),
            "description": f"{chan_label}·{direction_cn}：{desc_prefix}{money(delta):.2f}，力度降至{ratio:.0%}{extra_txt}",
        }

    def _get_segment_df(self, start, end) -> pd.DataFrame:
        mask = (self.df['date'] >= start) & (self.df['date'] <= end)
        return self.df[mask]
