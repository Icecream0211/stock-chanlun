import os
import sys
import unittest
from datetime import datetime, timedelta

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from chanlun.elements import Bi, XiangSegment
from chanlun.segment_detector import SegmentDetector


class SegmentDetectorTests(unittest.TestCase):
    def setUp(self):
        self.t0 = datetime(2026, 1, 2, 9, 30)

    def _bi(self, idx: int, direction: str, start_min: int, end_min: int, high: float, low: float) -> Bi:
        start = self.t0 + timedelta(minutes=start_min)
        end = self.t0 + timedelta(minutes=end_min)
        return Bi(
            id=f"bi_{idx}",
            start=start,
            end=end,
            direction=direction,
            high=high,
            low=low,
            start_price=low if direction == "up" else high,
            end_price=high if direction == "up" else low,
        )

    def _segment(self, idx: int, direction: str, start_min: int, end_min: int, high: float, low: float) -> XiangSegment:
        start = self.t0 + timedelta(minutes=start_min)
        end = self.t0 + timedelta(minutes=end_min)
        return XiangSegment(
            id=f"xiang_{idx}",
            start=start,
            end=end,
            direction=direction,
            high=high,
            low=low,
            start_price=low if direction == "up" else high,
            end_price=high if direction == "up" else low,
            bi_ids=[f"bi_{idx}a", f"bi_{idx}b", f"bi_{idx}c"],
            level=2,
        )

    def test_detect_segments_returns_empty_when_bis_less_than_three(self):
        detector = SegmentDetector(
            bis=[self._bi(1, "up", 0, 5, 11.0, 9.0), self._bi(2, "down", 5, 10, 11.0, 10.0)]
        )
        self.assertEqual(detector.detect_segments(), [])

    def _bis_from_points(self, points: list[float]) -> list[Bi]:
        bis = []
        for i, (start_price, end_price) in enumerate(zip(points, points[1:])):
            direction = "up" if end_price > start_price else "down"
            bis.append(self._bi(
                i + 1,
                direction,
                i * 5,
                (i + 1) * 5,
                max(start_price, end_price),
                min(start_price, end_price),
            ))
        return bis

    def test_detect_segments_uses_alternating_bis_and_shares_boundary(self):
        # 第3根向上笔终点 13 高于前后向上笔终点 11/12，确认上线段结束；
        # 剩余3笔形成一条尚未确认的下线段。
        bis = self._bis_from_points([9.0, 11.0, 10.0, 13.0, 9.0, 12.0, 8.0])
        detector = SegmentDetector(bis=bis)

        segments = detector.detect_segments()
        self.assertEqual(len(segments), 2)
        first, second = segments
        self.assertEqual(first.direction, "up")
        self.assertEqual(first.bi_ids, ["bi_1", "bi_2", "bi_3"])
        self.assertTrue(first.confirmed)
        self.assertEqual(second.direction, "down")
        self.assertEqual(second.bi_ids, ["bi_4", "bi_5", "bi_6"])
        self.assertFalse(second.confirmed)
        self.assertEqual(first.end, second.start)
        self.assertAlmostEqual(first.end_price, second.start_price)

    def test_detect_segments_rejects_disconnected_bis(self):
        bis = self._bis_from_points([9.0, 11.0, 10.0, 13.0])
        bis[1] = bis[1].model_copy(update={"start": bis[1].start + timedelta(minutes=1)})
        self.assertEqual(SegmentDetector(bis).detect_segments(), [])

    def test_detect_zhongshus_creates_one_from_three_overlapping_segments(self):
        segments = [
            self._segment(1, "up", 0, 10, 110.0, 100.0),
            self._segment(2, "down", 11, 20, 108.0, 102.0),
            self._segment(3, "up", 21, 30, 109.0, 103.0),
        ]
        detector = SegmentDetector(bis=[])

        zhongshus = detector.detect_zhongshus(segments)
        self.assertEqual(len(zhongshus), 1)
        zs = zhongshus[0]
        self.assertEqual(zs.id, "zs_1")
        self.assertEqual(zs.start, segments[0].start)
        self.assertEqual(zs.end, segments[2].end)
        self.assertAlmostEqual(zs.range_high, 108.0)
        self.assertAlmostEqual(zs.range_low, 103.0)
        self.assertEqual(zs.xiang_ids, ["xiang_1", "xiang_2", "xiang_3"])
        self.assertEqual(zs.source_type, "segment")

    def test_detect_bi_zhongshus_is_independent_from_segment_zhongshus(self):
        bis = self._bis_from_points([9.0, 13.0, 10.0, 12.0])
        detector = SegmentDetector(bis)

        zhongshus = detector.detect_bi_zhongshus()

        self.assertEqual(len(zhongshus), 1)
        self.assertEqual(zhongshus[0].id, "bi_zs_1")
        self.assertEqual(zhongshus[0].source_type, "bi")
        self.assertEqual(zhongshus[0].level, 1)
        self.assertAlmostEqual(zhongshus[0].range_high, 12.0)
        self.assertAlmostEqual(zhongshus[0].range_low, 10.0)

    def test_detect_zhongshus_extension_keeps_overlap_not_union(self):
        # 中枢延伸时区间应取所有段的交叠（收窄），而非并集扩张
        segments = [
            self._segment(1, "up", 0, 10, 110.0, 100.0),
            self._segment(2, "down", 11, 20, 108.0, 102.0),
            self._segment(3, "up", 21, 30, 109.0, 103.0),
            # 第4段向上突破但仍与中枢重叠：正确结果收窄到 [105, 108]，
            # 错误实现会扩张成 [103, 120]
            self._segment(4, "down", 31, 40, 120.0, 105.0),
        ]
        detector = SegmentDetector(bis=[])
        zhongshus = detector.detect_zhongshus(segments)

        self.assertEqual(len(zhongshus), 1)
        zs = zhongshus[0]
        self.assertAlmostEqual(zs.range_high, 108.0)
        self.assertAlmostEqual(zs.range_low, 105.0)
        self.assertEqual(zs.xiang_ids, ["xiang_1", "xiang_2", "xiang_3", "xiang_4"])

    def test_get_zhongshu_for_price_returns_latest_matching_zone(self):
        segments = [
            self._segment(1, "up", 0, 10, 110.0, 100.0),
            self._segment(2, "down", 11, 20, 108.0, 102.0),
            self._segment(3, "up", 21, 30, 109.0, 103.0),
            self._segment(4, "down", 31, 40, 130.0, 120.0),
            self._segment(5, "up", 41, 50, 128.0, 122.0),
            self._segment(6, "down", 51, 60, 126.0, 123.0),
        ]
        detector = SegmentDetector(bis=[])
        zhongshus = detector.detect_zhongshus(segments)

        self.assertEqual(len(zhongshus), 2)
        latest_match = detector.get_zhongshu_for_price(zhongshus, 124.0)
        self.assertIsNotNone(latest_match)
        self.assertEqual(latest_match.id, "zs_2")


if __name__ == "__main__":
    unittest.main()
