import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock

import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from chanlun.bi_detector import BiDetector
from chanlun.fenxing_detector import Fenxing


class BiDetectorFenxingCompressionTests(unittest.TestCase):
    def test_compress_keeps_most_extreme_of_same_type(self):
        t0 = datetime(2026, 1, 1)

        fenxings = [
            Fenxing(date=t0, type="top", high=10.0, low=9.0, index=1),
            # same type(top) but more extreme(high higher) -> should replace previous top
            Fenxing(date=t0 + timedelta(days=1), type="top", high=12.0, low=11.0, index=2),
            # same type(top) but less extreme -> should be ignored
            Fenxing(date=t0 + timedelta(days=2), type="top", high=11.0, low=10.0, index=3),
            Fenxing(date=t0 + timedelta(days=3), type="bottom", high=8.0, low=7.0, index=4),
            # same type(bottom) but more extreme(low lower) -> should replace previous bottom
            Fenxing(date=t0 + timedelta(days=4), type="bottom", high=7.5, low=6.5, index=5),
        ]

        compressed = BiDetector.compress_fenxings(fenxings)

        self.assertEqual(len(compressed), 2)
        self.assertEqual(compressed[0].type, "top")
        self.assertEqual(compressed[0].high, 12.0)
        self.assertEqual(compressed[0].index, 2)
        self.assertEqual(compressed[1].type, "bottom")
        self.assertEqual(compressed[1].low, 6.5)
        self.assertEqual(compressed[1].index, 5)

    def test_compress_keeps_earliest_when_same_type_prices_are_equal(self):
        t0 = datetime(2026, 1, 1)
        fenxings = [
            Fenxing(date=t0, type="top", high=12.0, low=10.0, index=1),
            Fenxing(date=t0 + timedelta(days=1), type="top", high=12.0, low=11.0, index=2),
        ]

        compressed = BiDetector.compress_fenxings(fenxings)

        self.assertEqual(len(compressed), 1)
        self.assertEqual(compressed[0].index, 1)

    def test_detect_builds_connected_alternating_bis(self):
        t0 = datetime(2026, 1, 1)
        frame = pd.DataFrame({
            "date": [t0 + timedelta(days=i) for i in range(16)],
            "open": [10.0] * 16,
            "high": [11.0] * 16,
            "low": [9.0] * 16,
            "close": [10.0] * 16,
            "volume": [100.0] * 16,
        })
        detector = BiDetector(frame)
        detector._fenxing_detector.klines = frame.copy()
        detector._fenxing_detector.detect = Mock(return_value=[
            Fenxing(date=t0 + timedelta(days=1), type="bottom", high=9.0, low=8.0, index=1),
            Fenxing(date=t0 + timedelta(days=5), type="top", high=13.0, low=12.0, index=5),
            Fenxing(date=t0 + timedelta(days=9), type="bottom", high=10.0, low=9.0, index=9),
            Fenxing(date=t0 + timedelta(days=13), type="top", high=14.0, low=13.0, index=13),
        ])

        bis = detector.detect(min_bars=5)

        self.assertEqual([b.direction for b in bis], ["up", "down", "up"])
        self.assertTrue(all(b.rule == "new" for b in bis))
        for previous, current in zip(bis, bis[1:]):
            self.assertEqual(previous.end, current.start)
            self.assertAlmostEqual(previous.end_price, current.start_price)

    def test_virtual_tail_connects_to_last_confirmed_bi_without_becoming_confirmed(self):
        t0 = datetime(2026, 1, 1)
        frame = pd.DataFrame({
            "date": [t0 + timedelta(days=i) for i in range(10)],
            "open": [10.0] * 10,
            "high": [11.0] * 10,
            "low": [9.0] * 10,
            "close": [10.0] * 10,
            "volume": [100.0] * 10,
        })
        detector = BiDetector(frame)
        detector._fenxing_detector.klines = pd.DataFrame({
            "date": [t0 + timedelta(days=i) for i in range(10)],
            "open": [10.0] * 10,
            "high": [10.0, 9.0, 10.0, 12.0, 14.0, 15.0, 14.0, 13.0, 12.0, 11.0],
            "low": [9.0, 8.0, 9.0, 10.0, 12.0, 13.0, 12.0, 10.0, 9.0, 7.0],
            "close": [10.0] * 10,
            "volume": [100.0] * 10,
        })
        detector._fenxing_detector.detect = Mock(return_value=[
            Fenxing(date=t0 + timedelta(days=1), type="bottom", high=9.0, low=8.0, index=1),
            Fenxing(date=t0 + timedelta(days=5), type="top", high=15.0, low=13.0, index=5),
        ])

        bis = detector.detect(min_bars=5, include_virtual=True)

        self.assertEqual(len(bis), 2)
        confirmed, virtual = bis
        self.assertTrue(confirmed.confirmed)
        self.assertFalse(virtual.confirmed)
        self.assertEqual(confirmed.end, virtual.start)
        self.assertAlmostEqual(confirmed.end_price, virtual.start_price)
        self.assertEqual(virtual.direction, "down")
        self.assertEqual(virtual.end, t0 + timedelta(days=9))
        self.assertAlmostEqual(virtual.end_price, 7.0)

    def test_virtual_tail_collapses_rejected_fractals_to_one_candidate(self):
        t0 = datetime(2026, 1, 1)
        frame = pd.DataFrame({
            "date": [t0 + timedelta(days=i) for i in range(12)],
            "open": [10.0] * 12,
            "high": [11.0] * 12,
            "low": [9.0] * 12,
            "close": [10.0] * 12,
            "volume": [100.0] * 12,
        })
        detector = BiDetector(frame)
        detector._fenxing_detector.klines = pd.DataFrame({
            "date": [t0 + timedelta(days=i) for i in range(12)],
            "open": [10.0] * 12,
            "high": [10, 9, 10, 12, 14, 15, 14, 13, 14, 16, 17, 18],
            "low": [9, 8, 9, 10, 12, 13, 12, 10, 11, 13, 15, 16],
            "close": [10.0] * 12,
            "volume": [100.0] * 12,
        })
        detector._fenxing_detector.detect = Mock(return_value=[
            Fenxing(date=t0 + timedelta(days=1), type="bottom", high=9.0, low=8.0, index=1),
            Fenxing(date=t0 + timedelta(days=5), type="top", high=15.0, low=13.0, index=5),
            # 与前一端点仅隔2根，不能确认成笔，但要作为虚线候选路径保留。
            Fenxing(date=t0 + timedelta(days=7), type="bottom", high=13.0, low=10.0, index=7),
        ])

        bis = detector.detect(min_bars=5, include_virtual=True)

        self.assertEqual([bi.confirmed for bi in bis], [True, False])
        self.assertEqual([bi.direction for bi in bis], ["up", "down"])
        self.assertEqual(bis[-1].rule, "virtual")
        for previous, current in zip(bis, bis[1:]):
            self.assertEqual(previous.end, current.start)
            self.assertAlmostEqual(previous.end_price, current.start_price)
        self.assertEqual(bis[-1].end, t0 + timedelta(days=7))
        self.assertAlmostEqual(bis[-1].end_price, 10.0)

    def test_new_pen_accepts_raw_five_bars_when_processed_gap_is_three(self):
        t0 = datetime(2026, 1, 1)
        frame = pd.DataFrame({
            "date": [t0 + timedelta(days=i) for i in range(8)],
            "open": [10.0] * 8,
            "high": [11.0] * 8,
            "low": [9.0] * 8,
            "close": [10.0] * 8,
            "volume": [100.0] * 8,
        })
        fenxings = [
            Fenxing(t0 + timedelta(days=1), "bottom", 10.0, 8.0, 1, raw_index=1),
            Fenxing(t0 + timedelta(days=5), "top", 13.0, 12.0, 4, raw_index=5),
        ]
        new_detector = BiDetector(frame, bi_mode="new")
        old_detector = BiDetector(frame, bi_mode="old")
        new_detector._fenxing_detector.klines = frame.copy()
        old_detector._fenxing_detector.klines = frame.copy()
        new_detector._fenxing_detector.detect = Mock(return_value=fenxings)
        old_detector._fenxing_detector.detect = Mock(return_value=fenxings)

        new_bis = new_detector.detect()
        old_bis = old_detector.detect()

        self.assertEqual(len(new_bis), 1)
        self.assertEqual(new_bis[0].rule, "new")
        self.assertEqual(old_bis, [])

    def test_new_pen_rejects_fractals_that_share_processed_kline(self):
        t0 = datetime(2026, 1, 1)
        frame = pd.DataFrame({
            "date": [t0 + timedelta(days=i) for i in range(8)],
            "open": [10.0] * 8,
            "high": [11.0] * 8,
            "low": [9.0] * 8,
            "close": [10.0] * 8,
            "volume": [100.0] * 8,
        })
        detector = BiDetector(frame, bi_mode="new")
        detector._fenxing_detector.klines = frame.copy()
        detector._fenxing_detector.detect = Mock(return_value=[
            Fenxing(t0 + timedelta(days=1), "bottom", 10.0, 8.0, 1, raw_index=1),
            Fenxing(t0 + timedelta(days=5), "top", 13.0, 12.0, 3, raw_index=5),
        ])

        self.assertEqual(detector.detect(), [])

    def test_detect_rejects_inverted_price_direction(self):
        t0 = datetime(2026, 1, 1)
        frame = pd.DataFrame({
            "date": [t0 + timedelta(days=i) for i in range(8)],
            "open": [10.0] * 8,
            "high": [11.0] * 8,
            "low": [9.0] * 8,
            "close": [10.0] * 8,
            "volume": [100.0] * 8,
        })
        detector = BiDetector(frame)
        detector._fenxing_detector.klines = frame.copy()
        detector._fenxing_detector.detect = Mock(return_value=[
            Fenxing(t0 + timedelta(days=1), "bottom", 11.0, 10.0, 1, raw_index=1),
            Fenxing(t0 + timedelta(days=5), "top", 9.0, 8.0, 5, raw_index=5),
        ])

        self.assertEqual(detector.detect(), [])

    def test_detect_rejects_end_that_is_not_interval_peak(self):
        t0 = datetime(2026, 1, 1)
        frame = pd.DataFrame({
            "date": [t0 + timedelta(days=i) for i in range(8)],
            "open": [10.0] * 8,
            "high": [10.0, 10.0, 15.0, 11.0, 12.0, 13.0, 12.0, 11.0],
            "low": [9.0] * 8,
            "close": [10.0] * 8,
            "volume": [100.0] * 8,
        })
        detector = BiDetector(frame)
        detector._fenxing_detector.klines = frame.copy()
        detector._fenxing_detector.detect = Mock(return_value=[
            Fenxing(t0 + timedelta(days=1), "bottom", 10.0, 8.0, 1, raw_index=1),
            Fenxing(t0 + timedelta(days=5), "top", 13.0, 12.0, 5, raw_index=5),
        ])

        self.assertEqual(detector.detect(), [])


if __name__ == "__main__":
    unittest.main()
