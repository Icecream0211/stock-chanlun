"""背驰检测边界：MACD 面积为 0 时不应抛异常。"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock

import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from chanlun.elements import Bi, Zhongshu  # noqa: E402
from ai.divergence import (  # noqa: E402
    DivergenceDetector,
    calculate_rsi,
    macd_area,
    macd_area_directional,
)


def _make_bi(d0: datetime, direction: str, high: float, low: float) -> Bi:
    return Bi(
        id="1",
        start=d0,
        end=d0 + timedelta(days=1),
        direction=direction,  # type: ignore[arg-type]
        high=high,
        low=low,
        start_price=low,
        end_price=high,
    )


def _make_bi_one_bar(
    d0: datetime, direction: str, high: float, low: float
) -> Bi:
    """start==end，对应日线序列上仅一根 K 线落入区间"""
    return Bi(
        id="1",
        start=d0,
        end=d0,
        direction=direction,  # type: ignore[arg-type]
        high=high,
        low=low,
        start_price=low,
        end_price=high,
    )


class DivergenceZeroMacdTests(unittest.TestCase):
    def test_check_divergence_no_raise_when_macd_sum_zero(self):
        # 常数 close -> MACD 柱可全为 0
        t0 = datetime(2020, 1, 1)
        rows = []
        for i in range(30):
            d = t0 + timedelta(days=i)
            rows.append(
                {
                    "date": d,
                    "open": 10.0,
                    "high": 10.0,
                    "low": 10.0,
                    "close": 10.0,
                    "volume": 1.0,
                }
            )
        df = pd.DataFrame(rows)
        up1 = _make_bi(t0, "up", 10.0, 9.0)
        up2 = _make_bi(t0 + timedelta(days=5), "up", 10.1, 9.1)
        up3 = _make_bi(t0 + timedelta(days=10), "up", 10.2, 9.2)
        up4 = _make_bi(t0 + timedelta(days=15), "up", 10.3, 9.1)
        bis = [up1, up2, up3, up4]
        det = DivergenceDetector(df)
        # 之前 macd1==0 会 ZeroDivisionError；现应安全返回 None
        out = det.check_divergence(bis)
        self.assertIsNone(out)


class DivergenceSegmentGuardTests(unittest.TestCase):
    def test_single_bar_segments_skipped(self):
        """笔区间内不足 MIN_BARS_PER_SEGMENT 根 K 线时不应给出背驰"""
        t0 = datetime(2020, 1, 1)
        rows = []
        for i in range(20):
            d = t0 + timedelta(days=i)
            rows.append(
                {
                    "date": d,
                    "open": 10.0 + i * 0.01,
                    "high": 10.05 + i * 0.01,
                    "low": 9.95 + i * 0.01,
                    "close": 10.0 + i * 0.01,
                    "volume": 1.0,
                }
            )
        df = pd.DataFrame(rows)
        # 四笔向上，每笔只覆盖单日 → 段内仅 1 根 K 线
        bis = [
            _make_bi_one_bar(t0 + timedelta(days=i), "up", 10.2, 9.8)
            for i in range(4)
        ]
        det = DivergenceDetector(df)
        self.assertIsNone(det.check_divergence(bis))


class MacdAreaDirectionalTests(unittest.TestCase):
    def test_directional_top_only_positive(self):
        s = pd.Series([1.0, -2.0, 3.0, np.nan])
        self.assertAlmostEqual(macd_area_directional(s, "top"), 4.0)
        self.assertAlmostEqual(macd_area_directional(s, "bottom"), 2.0)

    def test_directional_equals_abs_when_one_sign(self):
        pos = pd.Series([1.0, 2.0, 0.5])
        neg = pd.Series([-1.0, -2.0])
        self.assertAlmostEqual(macd_area_directional(pos, "top"), macd_area(pos))
        self.assertAlmostEqual(macd_area_directional(neg, "bottom"), macd_area(neg))


class DivergenceRsiTests(unittest.TestCase):
    def test_calculate_rsi_wilder_in_valid_range(self):
        t0 = datetime(2020, 1, 1)
        rows = []
        x = 50.0
        for i in range(60):
            d = t0 + timedelta(days=i)
            x += (-1) ** i * 0.8
            rows.append(
                {
                    "date": d,
                    "open": x,
                    "high": x + 0.5,
                    "low": x - 0.5,
                    "close": x,
                    "volume": 1.0,
                }
            )
        df = pd.DataFrame(rows)
        rsi = calculate_rsi(df, period=14)
        valid = rsi.iloc[14:].dropna()
        self.assertFalse(valid.empty)
        self.assertTrue((valid >= 0).all() and (valid <= 100).all())


class DivergenceLocationTests(unittest.TestCase):
    def test_result_contains_multi_factor_confirmation_and_chart_location(self):
        t0 = datetime(2020, 1, 1)
        raw = pd.DataFrame([
            {"date": t0 + timedelta(days=i), "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1}
            for i in range(10)
        ])
        detector = DivergenceDetector(raw)
        previous = _make_bi(t0, "up", 10.0, 9.0).model_copy(update={"id": "up-1"})
        current = _make_bi(t0 + timedelta(days=5), "up", 11.0, 9.5).model_copy(update={"id": "up-2"})
        detector._get_segment_df = Mock(side_effect=[
            pd.DataFrame({"bar": [1.0, 1.0], "rsi": [72.0, 70.0], "J": [90.0, 85.0]}),
            pd.DataFrame({"bar": [0.2, 0.2], "rsi": [62.0, 60.0], "J": [75.0, 70.0]}),
        ])

        result = detector._check_segment_divergence(previous, current, "top")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["datetime"], current.end)
        self.assertEqual(result["price"], current.high)
        self.assertEqual(result["confirmations"], ["MACD", "RSI", "KDJ"])
        self.assertEqual(result["confirm_count"], 3)
        self.assertEqual(result["evidence_grade"], "A")
        self.assertLessEqual(result["match_score"], 0.78)
        self.assertEqual(result["probability"], result["match_score"])
        self.assertEqual(result["chan_type"], "momentum")
        self.assertFalse(result["strict_chan"])
        self.assertTrue(result["is_multi"])
        self.assertEqual(result["previous_bi_id"], "up-1")
        self.assertEqual(result["current_bi_id"], "up-2")

    def test_c_grade_consolidation_match_score_is_capped(self):
        t0 = datetime(2020, 1, 1)
        raw = pd.DataFrame([
            {"date": t0 + timedelta(days=i), "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1}
            for i in range(10)
        ])
        detector = DivergenceDetector(raw, analysis_level="30min")
        previous = _make_bi(t0, "down", 18.0, 17.0).model_copy(update={"id": "d1"})
        current = _make_bi(t0 + timedelta(days=5), "down", 17.0, 16.0).model_copy(update={"id": "d2"})
        detector._get_segment_df = Mock(side_effect=[
            pd.DataFrame({"bar": [-2.0, -2.0], "rsi": [30.0, 28.0], "J": [20.0, 18.0]}),
            pd.DataFrame({"bar": [-0.1, -0.1], "rsi": [25.0, 22.0], "J": [15.0, 12.0]}),
        ])

        result = detector._check_segment_divergence(
            previous, current, "bottom", chan_type="consolidation"
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["evidence_grade"], "C")
        self.assertEqual(result["match_score"], 0.65)
        self.assertGreater(result["raw_strength_score"], result["match_score"])


class DivergenceChanStructureTests(unittest.TestCase):
    def test_single_center_first_and_third_same_direction_is_consolidation(self):
        t0 = datetime(2020, 1, 1)
        first = _make_bi(t0, "up", 11, 9).model_copy(update={"id": "b1"})
        middle = _make_bi(t0 + timedelta(days=1), "down", 11, 9.5).model_copy(update={"id": "b2"})
        third = _make_bi(t0 + timedelta(days=2), "up", 11.2, 9.7).model_copy(update={"id": "b3"})
        center = Zhongshu(
            id="zs1", start=first.start, end=third.end,
            range_high=11, range_low=9.7, xiang_ids=["b1", "b2", "b3"],
            level=1, source_type="bi", status="forming",
        )

        kind, related = DivergenceDetector._classify_chan_type(
            first, third, "top", [center]
        )

        self.assertEqual(kind, "consolidation")
        self.assertEqual([z.id for z in related], ["zs1"])

    def test_two_progressive_centers_and_completed_exit_is_trend_context(self):
        t0 = datetime(2020, 1, 1)
        incoming = _make_bi(t0, "up", 12, 10).model_copy(update={"id": "in"})
        outgoing = _make_bi(t0 + timedelta(days=12), "up", 14, 12).model_copy(update={"id": "out"})
        first = Zhongshu(
            id="zs1", start=t0 + timedelta(days=2), end=t0 + timedelta(days=5),
            range_high=11, range_low=10, xiang_ids=["a", "b", "c"],
            level=1, source_type="bi", status="completed", exit_direction="up",
        )
        last = Zhongshu(
            id="zs2", start=t0 + timedelta(days=7), end=t0 + timedelta(days=11),
            range_high=13, range_low=12, xiang_ids=["d", "e", "f"],
            level=1, source_type="bi", status="completed", exit_direction="up",
        )

        kind, related = DivergenceDetector._classify_chan_type(
            incoming, outgoing, "top", [first, last]
        )

        self.assertEqual(kind, "trend")
        self.assertEqual([z.id for z in related], ["zs1", "zs2"])

    def test_overlapping_centers_do_not_count_as_trend(self):
        t0 = datetime(2020, 1, 1)
        centers = [
            Zhongshu(
                id="zs1", start=t0, end=t0 + timedelta(days=2),
                range_high=11, range_low=9, xiang_ids=["a", "b", "c"],
                level=1, source_type="bi",
            ),
            Zhongshu(
                id="zs2", start=t0 + timedelta(days=3), end=t0 + timedelta(days=5),
                range_high=12, range_low=10, xiang_ids=["d", "e", "f"],
                level=1, source_type="bi",
            ),
        ]
        self.assertIsNone(DivergenceDetector._center_trend_direction(centers))


if __name__ == "__main__":
    unittest.main()
