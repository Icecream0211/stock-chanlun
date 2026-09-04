"""ChanlunEngine K 线输出与包含处理。"""
import os
import sys
import unittest
from datetime import datetime

import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from chanlun.bi_detector import BiDetector
from chanlun.engine import ChanlunEngine


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"date": datetime(2024, 1, 2), "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 1000.0},
        {"date": datetime(2024, 1, 3), "open": 10.4, "high": 10.8, "low": 10.0, "close": 10.6, "volume": 800.0},
        {"date": datetime(2024, 1, 4), "open": 10.7, "high": 12.0, "low": 10.6, "close": 11.8, "volume": 1200.0},
        {"date": datetime(2024, 1, 5), "open": 11.5, "high": 11.8, "low": 11.0, "close": 11.2, "volume": 900.0},
        {"date": datetime(2024, 1, 8), "open": 11.0, "high": 11.3, "low": 10.5, "close": 10.8, "volume": 700.0},
    ])


class ChanlunEngineKlinesTests(unittest.TestCase):
    def test_result_klines_keep_raw_window_length(self):
        raw = _sample_df()
        result = ChanlunEngine(raw).analyze(level="daily")
        self.assertEqual(len(result.klines), len(raw))

    def test_processed_klines_fewer_than_raw_after_inclusion(self):
        raw = _sample_df()
        processed = BiDetector(raw).processed_klines
        self.assertLess(len(processed), len(raw))

    def test_result_exposes_compact_inclusion_groups(self):
        result = ChanlunEngine(_sample_df()).analyze(level="daily")

        self.assertGreaterEqual(len(result.inclusions), 1)
        group = result.inclusions[0]
        self.assertGreaterEqual(group.count, 2)
        self.assertLess(group.start, group.end)
        self.assertIn(group.direction, ("up", "down"))


if __name__ == "__main__":
    unittest.main()
