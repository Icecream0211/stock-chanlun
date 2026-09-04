"""iFinD MCP 响应解析与首页兜底测试。"""
import os
import sys
import unittest
from unittest.mock import Mock, patch

import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from services import akshare_service, ifind_mcp_service


class IfindMcpServiceTests(unittest.TestCase):
    def setUp(self):
        ifind_mcp_service._cache.clear()
        with akshare_service._cache_lock:
            akshare_service._cache.clear()

    def test_exact_stock_info_is_normalized_for_search(self):
        payload = {
            "answer": (
                "|证券代码|证券简称|股票简称|公司中文名称|股票代码|\n"
                "|---|---|---|---|---|\n"
                "|002185.SZ|华天科技|华天科技|天水华天科技股份有限公司|002185|"
            )
        }
        with patch.object(ifind_mcp_service, "_call_tool", return_value=payload):
            frame = ifind_mcp_service.search_stocks("华天科技")

        self.assertEqual(frame.to_dict(orient="records"), [{"code": "002185", "name": "华天科技"}])
        self.assertEqual(frame.attrs["data_source"], "ifind_mcp")

    def test_hot_stock_markdown_uses_change_and_price_columns(self):
        payload = {
            "answer": (
                "|股票代码|股票简称|涨跌幅:前复权[20260901]|涨跌幅:前复权排名名次[20260901]|收盘价:不复权[20260901]|\n"
                "|---|---|---|---|---|\n"
                "|300189.SZ|神农种业|20.0318|1|7.55|"
            )
        }
        with patch.object(ifind_mcp_service, "_call_tool", return_value=payload):
            result = ifind_mcp_service.get_hot_stocks(10)

        self.assertEqual(result[0]["code"], "300189")
        self.assertEqual(result[0]["change_pct"], 20.03)
        self.assertEqual(result[0]["price"], 7.55)
        self.assertEqual(result[0]["data_source"], "ifind_mcp")

    def test_trending_news_is_normalized(self):
        payload = {
            "result": [
                {
                    "资讯标题": "A股市场新闻",
                    "资讯内容": "新闻摘要",
                    "URL": "https://example.com/news",
                    "信息来源": "测试来源",
                }
            ]
        }
        with patch.object(ifind_mcp_service, "_call_tool", return_value=payload):
            result = ifind_mcp_service.get_news(8)

        self.assertEqual(result[0]["title"], "A股市场新闻")
        self.assertEqual(result[0]["source"], "测试来源")
        self.assertEqual(result[0]["data_source"], "ifind_mcp")

    def test_index_table_builds_overview_and_market_breadth(self):
        payload = {
            "tables": [
                ["证券代码", "证券简称", "time", "最新价", "涨跌幅", "上涨家数", "下跌家数"],
                ["000001.SH", "上证指数", "2026-09-01 12:00:00", "3987.56", "0.03", "1480", "833"],
                ["399001.SZ", "深证成指", "2026-09-01 12:00:00", "13933.1", "-0.58", "1858", "1024"],
            ]
        }
        with patch.object(ifind_mcp_service, "_call_tool", return_value=payload):
            result = ifind_mcp_service.get_market_overview()

        self.assertEqual(result["indices"]["sh"]["price"], 3987.56)
        self.assertEqual(result["indices"]["sh"]["instrument_id"], "sh000001")
        self.assertEqual(result["indices"]["sz"]["change_pct"], -0.58)
        self.assertEqual(result["market_breadth"]["advancers"], 3338)
        self.assertEqual(result["market_breadth"]["decliners"], 1857)

    def test_news_switches_to_ifind_after_all_legacy_sources_fail(self):
        fallback = [{"title": "iFinD 新闻", "data_source": "ifind_mcp"}]
        with (
            patch.object(akshare_service, "_fetch_em_breaking_news", return_value=[]),
            patch.object(akshare_service, "_fetch_ths_news", return_value=[]),
            patch.object(akshare_service, "_fetch_em_article_news", return_value=[]),
            patch.object(ifind_mcp_service, "get_news", return_value=fallback) as ifind_mock,
        ):
            result = akshare_service.get_stock_news(8)

        ifind_mock.assert_called_once_with(8)
        self.assertEqual(result, fallback)

    def test_hot_stocks_switch_to_ifind_after_all_legacy_sources_fail(self):
        fallback = [{"code": "300189", "name": "神农种业", "data_source": "ifind_mcp"}]
        with (
            patch.object(akshare_service, "_fetch_em_hot_stocks", return_value=[]),
            patch.object(akshare_service, "_fetch_ths_hot_stocks", return_value=[]),
            patch.object(akshare_service, "_fetch_sina_hot_stocks", return_value=[]),
            patch.object(ifind_mcp_service, "get_hot_stocks", return_value=fallback) as ifind_mock,
        ):
            result = akshare_service.get_daily_hot_stocks(10)

        ifind_mock.assert_called_once_with(10)
        self.assertEqual(result, fallback)

    def test_search_switches_to_ifind_when_sina_returns_no_match(self):
        response = Mock(content='var suggestvalue="N";'.encode("gbk"))
        client = Mock()
        client.get.return_value = response
        fallback = pd.DataFrame([{"code": "002185", "name": "华天科技"}])
        fallback.attrs["data_source"] = "ifind_mcp"
        with (
            patch.object(akshare_service, "_get_client", return_value=client),
            patch.object(ifind_mcp_service, "search_stocks", return_value=fallback) as ifind_mock,
        ):
            result = akshare_service.search_stocks("华天科技")

        ifind_mock.assert_called_once_with("华天科技", limit=20)
        self.assertEqual(result.iloc[0]["code"], "002185")
        self.assertEqual(result.attrs["data_source"], "ifind_mcp")

    def test_market_overview_fills_missing_legacy_indices_from_ifind(self):
        fallback = {
            "indices": {"sh": {"code": "000001", "name": "上证指数", "price": 3987.56}},
            "market_breadth": {"advancers": 3338, "decliners": 1857, "unchanged": 0},
        }
        with (
            patch.object(
                akshare_service,
                "_normalize_index_row",
                side_effect=lambda code, name: {"code": code, "name": name, "price": 0, "change_pct": 0},
            ),
            patch.object(
                akshare_service,
                "get_a_share_market_breadth",
                return_value={"advancers": 0, "decliners": 0, "unchanged": 0},
            ),
            patch.object(akshare_service, "get_all_industry_boards", return_value=[]),
            patch.object(ifind_mcp_service, "get_market_overview", return_value=fallback) as ifind_mock,
        ):
            result = akshare_service.get_market_overview_bundle()

        ifind_mock.assert_called_once_with()
        self.assertEqual(result["indices"]["sh"]["price"], 3987.56)
        self.assertEqual(result["indices"]["sh"]["instrument_id"], "sh000001")
        self.assertEqual(result["market_breadth"]["advancers"], 3338)
        self.assertEqual(result["data_sources"], ["ifind_mcp"])
        self.assertFalse(result["stale"])


if __name__ == "__main__":
    unittest.main()
