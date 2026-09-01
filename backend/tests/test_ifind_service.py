"""iFinD 适配器与统一行情回退测试。"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config
from services import ifind_service, market_data_service


def _kline_result() -> SimpleNamespace:
    return SimpleNamespace(
        errorcode=0,
        errmsg="",
        data=pd.DataFrame(
            {
                "time": ["2026-08-28", "2026-08-31"],
                "open": [10.0, 10.5],
                "high": [10.8, 11.0],
                "low": [9.9, 10.4],
                "close": [10.6, 10.9],
                "volume": [1000, 1200],
            }
        ),
    )


class FakeIfindSdk:
    def __init__(self):
        self.hq_args = None
        self.hf_args = None
        self.rq_args = None

    def THS_HQ(self, *args):
        self.hq_args = args
        return _kline_result()

    def THS_HF(self, *args):
        self.hf_args = args
        return _kline_result()

    def THS_RQ(self, *args):
        self.rq_args = args
        return SimpleNamespace(
            errorcode=0,
            errmsg="",
            data=pd.DataFrame(
                {
                    "THSCODE": ["600519.SH", "000001.SZ"],
                    "latest": [1500.0, 12.5],
                    "open": [1490.0, 12.3],
                    "high": [1510.0, 12.8],
                    "low": [1488.0, 12.2],
                    "latestVolume": [100.0, 200.0],
                    "latestAmount": [150000.0, 2500.0],
                }
            ),
        )


class IfindServiceTests(unittest.TestCase):
    def setUp(self):
        ifind_service._kline_cache.clear()
        ifind_service._minute_cache.clear()
        ifind_service._quote_cache.clear()

    def test_code_conversion_covers_three_exchanges(self):
        self.assertEqual(ifind_service.to_ifind_code("sh600519"), "600519.SH")
        self.assertEqual(ifind_service.to_ifind_code("000001"), "000001.SZ")
        self.assertEqual(ifind_service.to_ifind_code("832000"), "832000.BJ")

    def test_daily_kline_uses_hq_and_normalizes_columns(self):
        sdk = FakeIfindSdk()
        with patch.object(ifind_service, "_ensure_login", return_value=sdk):
            frame = ifind_service.get_ifind_kline("600519", "daily", limit=100)

        self.assertEqual(list(frame.columns), ["date", "open", "close", "high", "low", "volume"])
        self.assertEqual(frame.attrs["data_source"], "ifind")
        self.assertEqual(sdk.hq_args[0], "600519.SH")
        self.assertIn("Interval:D", sdk.hq_args[2])
        self.assertIn("CPS:forward1", sdk.hq_args[2])

    def test_minute_kline_uses_hf_interval(self):
        sdk = FakeIfindSdk()
        with patch.object(ifind_service, "_ensure_login", return_value=sdk):
            frame = ifind_service.get_ifind_kline("000001", "30", adjust="hfq", limit=100)

        self.assertEqual(len(frame), 2)
        self.assertEqual(sdk.hf_args[0], "000001.SZ")
        self.assertIn("Interval:30", sdk.hf_args[2])
        self.assertIn("CPS:backward1", sdk.hf_args[2])

    def test_http_transport_uses_official_history_endpoint(self):
        with (
            patch.object(config, "IFIND_ACCESS_TOKEN", "test-access-token"),
            patch.object(config, "IFIND_REFRESH_TOKEN", ""),
            patch.object(ifind_service, "_http_post", return_value=_kline_result()) as post_mock,
        ):
            frame = ifind_service.get_ifind_kline("600519", "weekly", limit=100)

        self.assertEqual(len(frame), 2)
        endpoint, payload = post_mock.call_args.args
        self.assertEqual(endpoint, "/api/v1/cmd_history_quotation")
        self.assertEqual(payload["codes"], "600519.SH")
        self.assertEqual(payload["functionpara"]["Interval"], "W")

    def test_realtime_quote_normalizes_ifind_fields(self):
        sdk = FakeIfindSdk()
        with patch.object(ifind_service, "_ensure_login", return_value=sdk):
            frame = ifind_service.get_ifind_realtime_quote(["600519", "000001"])

        self.assertEqual(frame["代码"].tolist(), ["600519", "000001"])
        self.assertEqual(frame["最新价"].tolist(), [1500.0, 12.5])
        self.assertTrue(frame["昨收"].isna().all())
        self.assertIn("latestAmount", sdk.rq_args[1])


class MarketDataServiceTests(unittest.TestCase):
    def test_kline_falls_back_to_legacy_when_ifind_is_empty(self):
        legacy = _kline_result().data.rename(columns={"time": "date"})
        with (
            patch.object(config, "IFIND_ENABLED", True),
            patch.object(config, "MARKET_DATA_SOURCES", ("ifind", "legacy")),
            patch.object(market_data_service, "get_ifind_kline", return_value=pd.DataFrame()),
            patch.object(market_data_service, "get_legacy_kline_hist", return_value=legacy),
        ):
            frame = market_data_service.get_kline_hist("600519", "daily")

        self.assertEqual(frame.attrs["data_source"], "legacy")
        self.assertEqual(len(frame), 2)

    def test_ifind_quote_keeps_price_and_legacy_fills_metadata(self):
        ifind = pd.DataFrame(
            [{"代码": "600519", "名称": "", "最新价": 1500.0, "涨跌幅": None, "昨收": None}]
        )
        legacy = pd.DataFrame(
            [{"代码": "600519", "名称": "贵州茅台", "最新价": 1498.0, "涨跌幅": 1.2, "昨收": 1482.2}]
        )
        with (
            patch.object(config, "IFIND_ENABLED", True),
            patch.object(config, "MARKET_DATA_SOURCES", ("ifind", "legacy")),
            patch.object(market_data_service, "get_ifind_realtime_quote", return_value=ifind),
            patch.object(market_data_service, "get_legacy_realtime_quote", return_value=legacy),
        ):
            frame = market_data_service.get_realtime_quote(["600519"])

        self.assertEqual(frame.iloc[0]["最新价"], 1500.0)
        self.assertEqual(frame.iloc[0]["名称"], "贵州茅台")
        self.assertEqual(frame.iloc[0]["昨收"], 1482.2)
        self.assertEqual(frame.attrs["data_source"], "ifind+legacy")

    def test_disabled_ifind_does_not_call_sdk_adapter(self):
        legacy = pd.DataFrame([{"代码": "000001", "最新价": 12.5}])
        with (
            patch.object(config, "IFIND_ENABLED", False),
            patch.object(config, "MARKET_DATA_SOURCES", ("ifind", "legacy")),
            patch.object(market_data_service, "get_ifind_realtime_quote") as ifind_mock,
            patch.object(market_data_service, "get_legacy_realtime_quote", return_value=legacy),
        ):
            frame = market_data_service.get_realtime_quote(["000001"])

        ifind_mock.assert_not_called()
        self.assertEqual(frame.attrs["data_source"], "legacy")


if __name__ == "__main__":
    unittest.main()
