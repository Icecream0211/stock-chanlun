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
        detector._fenxing_detector.detect = Mock(return_value=[
            Fenxing(date=t0 + timedelta(days=1), type="bottom", high=9.0, low=8.0, index=1),
            Fenxing(date=t0 + timedelta(days=5), type="top", high=13.0, low=12.0, index=5),
            Fenxing(date=t0 + timedelta(days=9), type="bottom", high=10.0, low=9.0, index=9),
            Fenxing(date=t0 + timedelta(days=13), type="top", high=14.0, low=13.0, index=13),
        ])

        bis = detector.detect(min_bars=5)

        self.assertEqual([b.direction for b in bis], ["up", "down", "up"])
        for previous, current in zip(bis, bis[1:]):
            self.assertEqual(previous.end, current.start)
            self.assertAlmostEqual(previous.end_price, current.start_price)


if __name__ == "__main__":
    unittest.main()
