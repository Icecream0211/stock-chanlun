import os
import sys
import unittest
from datetime import datetime, timedelta

import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from chanlun.fenxing_detector import FenxingDetector


class FenxingInclusionTests(unittest.TestCase):
    def _df(self, highs: list[float], lows: list[float]) -> pd.DataFrame:
        t0 = datetime(2026, 1, 1)
        return pd.DataFrame(
            [
                {
                    "date": t0 + timedelta(days=i),
                    "open": low,
                    "high": high,
                    "low": low,
                    "close": high,
                    "volume": 1,
                }
                for i, (high, low) in enumerate(zip(highs, lows))
            ]
        )

    def test_upward_inclusion_keeps_higher_high_and_higher_low(self):
        detector = FenxingDetector(self._df([10, 12, 11], [8, 9, 10]))

        merged = detector.klines.iloc[1]
        self.assertEqual(len(detector.klines), 2)
        self.assertEqual(merged["high"], 12)
        self.assertEqual(merged["low"], 10)
        self.assertEqual(merged["raw_start_idx"], 1)
        self.assertEqual(merged["raw_end_idx"], 2)
        self.assertEqual(merged["high_raw_idx"], 1)
        self.assertEqual(merged["low_raw_idx"], 2)

    def test_downward_inclusion_keeps_lower_high_and_lower_low(self):
        detector = FenxingDetector(self._df([12, 10, 9.5], [10, 8, 8.5]))

        merged = detector.klines.iloc[1]
        self.assertEqual(len(detector.klines), 2)
        self.assertEqual(merged["high"], 9.5)
        self.assertEqual(merged["low"], 8)
        self.assertEqual(merged["raw_start_idx"], 1)
        self.assertEqual(merged["raw_end_idx"], 2)
        self.assertEqual(merged["high_raw_idx"], 2)
        self.assertEqual(merged["low_raw_idx"], 1)

    def test_top_fractal_uses_original_high_bar_as_endpoint(self):
        frame = self._df([9, 12, 11, 10], [7, 8, 9, 6])
        detector = FenxingDetector(frame)

        fenxings = detector.detect()

        self.assertEqual(len(fenxings), 1)
        top = fenxings[0]
        self.assertEqual(top.type, "top")
        self.assertEqual(top.index, 1)
        self.assertEqual(top.raw_index, 1)
        self.assertEqual(top.raw_start_idx, 1)
        self.assertEqual(top.raw_end_idx, 2)
        self.assertEqual(top.date, frame.iloc[1]["date"])


if __name__ == "__main__":
    unittest.main()
