"""缠论分析辅助：缓存键与级别映射。"""
import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.chanlun_analysis import (
    DEFAULT_KLINE_LIMIT,
    SCREENING_KLINE_LIMIT,
    chanlun_cache_key,
    resolve_kline_limit,
    level_to_period,
)


class ChanlunAnalysisHelperTests(unittest.TestCase):
    def test_cache_key_includes_kline_limit(self):
        k_full = chanlun_cache_key("600519", "daily", DEFAULT_KLINE_LIMIT)
        k_screen = chanlun_cache_key("600519", "daily", SCREENING_KLINE_LIMIT)
        self.assertNotEqual(k_full, k_screen)
        self.assertIn(str(DEFAULT_KLINE_LIMIT), k_full)
        self.assertIn(str(SCREENING_KLINE_LIMIT), k_screen)

    def test_level_to_period_weekly_monthly(self):
        self.assertEqual(level_to_period("weekly"), "weekly")
        self.assertEqual(level_to_period("monthly"), "monthly")
        self.assertEqual(level_to_period("daily"), "daily")

    def test_intraday_date_range_expands_window_and_separates_cache(self):
        limit = resolve_kline_limit("30min", "2024-09-08", "2026-09-09")

        # 两年 30 分钟 K 约四千根，不能退化成最近 500 根。
        self.assertGreaterEqual(limit, 4000)
        self.assertLessEqual(limit, 5000)
        self.assertNotEqual(
            chanlun_cache_key("002202", "30min", limit, "2024-09-08", "2026-09-09"),
            chanlun_cache_key("002202", "30min", limit, "2026-06-01", "2026-09-09"),
        )



if __name__ == "__main__":
    unittest.main()
