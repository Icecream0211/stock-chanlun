import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from routers.chanlun_routes import _apply_counter_trend_guard  # noqa: E402


class CounterTrendGuardTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "direction": "买入",
            "confidence": 0.55,
            "risk_level": "中",
            "entry_price": 16.52,
            "stop_loss": 16.4,
            "take_profit": 17.0,
            "holding_period": "1-3天",
            "description": "短线反弹",
        }
        self.divergence = {
            "type": "bottom",
            "chan_type": "consolidation",
            "evidence_grade": "C",
            "rsi_confirm": False,
            "kdj_confirm": False,
            "datetime": "2026-08-25 10:00:00",
        }
        self.resonance = {
            "direction": "卖出",
            "trends": [
                {"level": "30min", "trend": "下跌"},
                {"level": "daily", "trend": "下跌"},
                {"level": "weekly", "trend": "下跌"},
            ],
        }

    def test_c_grade_bottom_divergence_is_downgraded_to_observation(self):
        result = _apply_counter_trend_guard(
            self.payload,
            trend="下跌",
            divergence=self.divergence,
            resonance=self.resonance,
            signals=[],
        )
        self.assertEqual(result["direction"], "观望")
        self.assertLessEqual(result["confidence"], 0.49)
        self.assertEqual(result["risk_level"], "高")
        self.assertIsNone(result["entry_price"])
        self.assertTrue(result["decision_guard"]["applied"])
        self.assertIn("反弹观察", result["description"])

    def test_rsi_confirmation_keeps_original_recommendation(self):
        divergence = {**self.divergence, "rsi_confirm": True, "evidence_grade": "B"}
        result = _apply_counter_trend_guard(
            self.payload,
            trend="下跌",
            divergence=divergence,
            resonance=self.resonance,
            signals=[],
        )
        self.assertEqual(result["direction"], "买入")
        self.assertFalse(result["decision_guard"]["applied"])

    def test_confirmed_third_buy_keeps_original_recommendation(self):
        result = _apply_counter_trend_guard(
            self.payload,
            trend="下跌",
            divergence=self.divergence,
            resonance=self.resonance,
            signals=[{"type": "三买", "datetime": "2026-08-26 10:00:00"}],
        )
        self.assertEqual(result["direction"], "买入")
        self.assertFalse(result["decision_guard"]["applied"])


if __name__ == "__main__":
    unittest.main()
