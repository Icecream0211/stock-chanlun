import os
import sys
import unittest
from datetime import datetime, timedelta

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from chanlun.elements import Bi, XiangSegment, Zhongshu
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

    def test_detect_segments_keeps_short_tail_connected_as_unconfirmed(self):
        # 前3笔确认上线段，余下仅2笔尚不足3笔线段；绘图仍应从同一端点接出虚线尾段。
        bis = self._bis_from_points([9.0, 11.0, 10.0, 13.0, 9.0, 12.0])

        segments = SegmentDetector(bis).detect_segments()

        self.assertEqual(len(segments), 2)
        confirmed, pending = segments
        self.assertTrue(confirmed.confirmed)
        self.assertFalse(pending.confirmed)
        self.assertEqual(pending.bi_ids, ["bi_4", "bi_5"])
        self.assertEqual(confirmed.end, pending.start)
        self.assertAlmostEqual(confirmed.end_price, pending.start_price)

    def test_detect_segments_keeps_residual_after_unconfirmed_tail_connected(self):
        # 未确认尾段按同向终点收在第3笔，剩余1笔继续作为下一条候选尾段显示。
        bis = self._bis_from_points([9.0, 11.0, 10.0, 13.0, 9.0, 12.0, 8.0, 14.0])

        segments = SegmentDetector(bis).detect_segments()

        self.assertEqual(len(segments), 3)
        self.assertTrue(segments[0].confirmed)
        self.assertFalse(segments[1].confirmed)
        self.assertFalse(segments[2].confirmed)
        self.assertEqual(segments[2].bi_ids, ["bi_7"])
        self.assertEqual(segments[1].end, segments[2].start)
        self.assertAlmostEqual(segments[1].end_price, segments[2].start_price)

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

    def test_detect_zhongshus_extension_keeps_initial_core_fixed(self):
        # 标准中枢由前三段固定 [ZD, ZG]，延伸只增加时间和外围波动范围。
        segments = [
            self._segment(1, "up", 0, 10, 110.0, 100.0),
            self._segment(2, "down", 11, 20, 108.0, 102.0),
            self._segment(3, "up", 21, 30, 109.0, 103.0),
            # 第4段仍与中枢重叠，但不能把固定核心收窄到 [105, 108]。
            self._segment(4, "down", 31, 40, 120.0, 105.0),
        ]
        detector = SegmentDetector(bis=[])
        zhongshus = detector.detect_zhongshus(segments)

        self.assertEqual(len(zhongshus), 1)
        zs = zhongshus[0]
        self.assertAlmostEqual(zs.range_high, 108.0)
        self.assertAlmostEqual(zs.range_low, 103.0)
        self.assertAlmostEqual(zs.zg, 108.0)
        self.assertAlmostEqual(zs.zd, 103.0)
        self.assertAlmostEqual(zs.gg, 120.0)
        self.assertAlmostEqual(zs.dd, 100.0)
        self.assertEqual(zs.status, "extended")
        self.assertEqual(zs.xiang_ids, ["xiang_1", "xiang_2", "xiang_3", "xiang_4"])

    def test_detect_zhongshus_keeps_crossing_structure_as_extension(self):
        segments = [
            self._segment(1, "up", 0, 10, 110.0, 100.0),
            self._segment(2, "down", 11, 20, 108.0, 102.0),
            self._segment(3, "up", 21, 30, 109.0, 103.0),
            self._segment(4, "down", 31, 40, 112.0, 106.0),  # 回抽重入
            self._segment(5, "up", 41, 50, 112.0, 106.0),
        ]

        zhongshus = SegmentDetector(bis=[]).detect_zhongshus(segments)

        self.assertEqual(len(zhongshus), 1)
        zs = zhongshus[0]
        # 两段均仍与 [103, 108] 有严格交集；即使端点在核心外，也仍是延伸。
        self.assertEqual(zs.status, "extended")
        self.assertIsNone(zs.exit_direction)
        self.assertEqual(zs.end, segments[4].end)
        self.assertEqual(zs.structure_count, 5)
        self.assertEqual(zs.extension_count, 2)

    def test_detect_zhongshus_keeps_tail_crossing_core_as_extension(self):
        segments = [
            self._segment(1, "up", 0, 10, 110.0, 100.0),
            self._segment(2, "down", 11, 20, 108.0, 102.0),
            self._segment(3, "up", 21, 30, 109.0, 103.0),
            # 第四段仍穿过核心，即使收在核心下方，也不能把它当作离开。
            self._segment(4, "down", 31, 40, 106.0, 95.0),
        ]

        zhongshus = SegmentDetector(bis=[]).detect_zhongshus(segments)

        self.assertEqual(len(zhongshus), 1)
        zs = zhongshus[0]
        self.assertEqual(zs.status, "extended")
        self.assertIsNone(zs.exit_direction)
        self.assertEqual(zs.end, segments[3].end)

    def test_bi_center_ends_on_first_wholly_disjoint_pen_without_waiting_for_return(self):
        # 笔中枢固定核心为前三笔的 [11, 14]。第 4 笔虽穿过核心后收在下方，
        # 仍属延伸；第 5 笔整个价格区间 [8, 10] 已完全在 ZD 下方，按锁定
        # 口径旧中枢此刻立即结束，不能等第 6 笔“回抽失败”才完成。
        bis = self._bis_from_points([10.0, 14.0, 11.0, 15.0, 8.0, 10.0])

        zhongshus = SegmentDetector(bis).detect_bi_zhongshus()

        self.assertEqual(len(zhongshus), 1)
        center = zhongshus[0]
        self.assertEqual(center.status, "completed")
        self.assertEqual(center.exit_direction, "down")
        self.assertEqual(center.xiang_ids, ["bi_1", "bi_2", "bi_3", "bi_4"])

    def test_first_disjoint_structure_is_next_center_search_start(self):
        segments = [
            self._segment(1, "up", 0, 10, 110.0, 100.0),
            self._segment(2, "down", 11, 20, 108.0, 102.0),
            self._segment(3, "up", 21, 30, 109.0, 103.0),
            # 第 4 段整体高于初始核心 [103, 108]，它既结束旧中枢，也必须
            # 作为下一组三段的首段，不能被旧状态机吞掉。
            self._segment(4, "down", 31, 40, 120.0, 111.0),
            self._segment(5, "up", 41, 50, 121.0, 112.0),
            self._segment(6, "down", 51, 60, 119.0, 113.0),
        ]

        zhongshus = SegmentDetector(bis=[]).detect_zhongshus(segments)

        self.assertEqual(len(zhongshus), 2)
        self.assertEqual(zhongshus[0].status, "completed")
        self.assertEqual(zhongshus[0].xiang_ids, ["xiang_1", "xiang_2", "xiang_3"])
        self.assertEqual(zhongshus[1].xiang_ids, ["xiang_4", "xiang_5", "xiang_6"])

    def test_same_level_bi_zhongshus_split_six_pens_into_two_consolidations(self):
        bis = self._bis_from_points([100.0, 110.0, 102.0, 109.0, 103.0, 108.0, 104.0])

        zhongshus = SegmentDetector(bis).detect_same_level_bi_zhongshus()

        self.assertEqual(len(zhongshus), 2)
        self.assertEqual(zhongshus[0].xiang_ids, ["bi_1", "bi_2", "bi_3"])
        self.assertEqual(zhongshus[1].xiang_ids, ["bi_4", "bi_5", "bi_6"])
        self.assertTrue(all(z.decomposition == "same_level" for z in zhongshus))

    def test_same_level_bi_zhongshus_do_not_cross_completed_segment_boundary(self):
        # 两个相反方向的完整线段各自都有三笔重叠。全局笔中枢若跨界延伸，
        # 会把它们误画成同一个大框；线段分解必须分别保留两个局部中枢。
        bis = self._bis_from_points([10.0, 14.0, 11.0, 15.0, 10.0, 14.0, 9.0])
        segments = [
            self._segment(1, "up", 0, 15, 15.0, 10.0).model_copy(update={
                "bi_ids": ["bi_1", "bi_2", "bi_3"],
                "confirmed": True,
            }),
            self._segment(2, "down", 15, 30, 15.0, 9.0).model_copy(update={
                "bi_ids": ["bi_4", "bi_5", "bi_6"],
                "confirmed": True,
            }),
        ]

        zhongshus = SegmentDetector(bis).detect_same_level_bi_zhongshus(segments)

        self.assertEqual(len(zhongshus), 2)
        self.assertEqual(zhongshus[0].xiang_ids, ["bi_1", "bi_2", "bi_3"])
        self.assertEqual(zhongshus[1].xiang_ids, ["bi_4", "bi_5", "bi_6"])
        self.assertTrue(all(z.status == "forming" for z in zhongshus))
        self.assertTrue(all(z.decomposition == "same_level" for z in zhongshus))

    def test_same_level_tail_center_with_virtual_pen_is_only_a_candidate(self):
        bis = self._bis_from_points([10.0, 14.0, 11.0, 15.0, 10.0, 14.0, 9.0, 10.0, 9.0, 10.0])
        bis[-1] = bis[-1].model_copy(update={"confirmed": False})
        segments = [
            self._segment(1, "up", 0, 15, 15.0, 10.0).model_copy(update={
                "bi_ids": ["bi_1", "bi_2", "bi_3"],
                "confirmed": True,
            }),
            self._segment(2, "down", 15, 30, 15.0, 9.0).model_copy(update={
                "bi_ids": ["bi_4", "bi_5", "bi_6"],
                "confirmed": True,
            }),
            self._segment(3, "up", 30, 45, 10.0, 9.0).model_copy(update={
                "bi_ids": ["bi_7", "bi_8", "bi_9"],
                "confirmed": False,
            }),
        ]

        zhongshus = SegmentDetector(bis).detect_same_level_bi_zhongshus(segments)

        candidate = zhongshus[-1]
        self.assertEqual(candidate.xiang_ids, ["bi_7", "bi_8", "bi_9"])
        self.assertFalse(candidate.confirmed)
        self.assertEqual(candidate.decomposition, "same_level")

    def test_confirmed_pullback_below_core_completes_extended_center(self):
        segments = [
            self._segment(
                idx,
                "down" if idx % 2 else "up",
                (idx - 1) * 10,
                idx * 10,
                110.0 + (idx % 3),
                100.0 + (idx % 2),
            )
            for idx in range(1, 9)
        ]
        # 第9段穿过核心后向下离开；第10段反弹高点仍低于核心下沿。
        segments.extend([
            self._segment(9, "down", 80, 90, 106.0, 95.0),
            self._segment(10, "up", 90, 100, 100.5, 96.0),
        ])

        zhongshus = SegmentDetector(bis=[]).detect_zhongshus(segments)

        child = next(z for z in zhongshus if z.status != "expanded")
        self.assertEqual(child.status, "completed")
        self.assertEqual(child.exit_direction, "down")
        self.assertEqual(child.structure_count, 9)
        self.assertEqual(child.end, segments[8].end)
        self.assertNotIn(segments[9].id, child.xiang_ids)

    def test_detect_zhongshus_leave_and_failed_return_completes_center(self):
        segments = [
            self._segment(1, "up", 0, 10, 110.0, 100.0),
            self._segment(2, "down", 11, 20, 108.0, 102.0),
            self._segment(3, "up", 21, 30, 109.0, 103.0),
            self._segment(4, "down", 31, 40, 120.0, 111.0),
            self._segment(5, "up", 41, 50, 121.0, 112.0),
        ]

        zhongshus = SegmentDetector(bis=[]).detect_zhongshus(segments)

        self.assertEqual(len(zhongshus), 1)
        zs = zhongshus[0]
        self.assertEqual(zs.status, "completed")
        self.assertEqual(zs.exit_direction, "up")
        self.assertEqual(zs.end, segments[2].end)
        self.assertEqual(zs.xiang_ids, ["xiang_1", "xiang_2", "xiang_3"])

    def test_detect_zhongshus_rejects_single_price_core(self):
        segments = [
            self._segment(1, "up", 0, 10, 110.0, 100.0),
            self._segment(2, "down", 11, 20, 115.0, 105.0),
            self._segment(3, "up", 21, 30, 120.0, 110.0),
        ]

        zhongshus = SegmentDetector(bis=[]).detect_zhongshus(segments)

        self.assertEqual(zhongshus, [])

    def test_detect_zhongshus_nine_structure_extension_creates_parent_center(self):
        segments = [
            self._segment(
                idx,
                "up" if idx % 2 else "down",
                (idx - 1) * 10,
                idx * 10,
                110.0 + (idx % 3),
                100.0 + (idx % 2),
            )
            for idx in range(1, 10)
        ]

        zhongshus = SegmentDetector(bis=[], include_expansion=True).detect_zhongshus(segments)

        self.assertEqual(len(zhongshus), 2)
        child = next(z for z in zhongshus if z.status != "expanded")
        parent = next(z for z in zhongshus if z.status == "expanded")
        self.assertEqual(parent.expansion_type, "nine_structure")
        self.assertEqual(parent.level, child.level + 1)
        self.assertEqual(parent.child_ids, [child.id])
        self.assertEqual(child.parent_id, parent.id)
        # 高一级核心必须由三个 3 结构组合走势重新求交集，不能复制子中枢核心。
        self.assertAlmostEqual(child.range_low, 101.0)
        self.assertAlmostEqual(child.range_high, 110.0)
        self.assertAlmostEqual(parent.range_low, 100.0)
        self.assertAlmostEqual(parent.range_high, 112.0)
        self.assertEqual(parent.structure_count, 9)

    def test_nine_structure_parent_ignores_unconfirmed_partial_group(self):
        segments = [
            self._segment(
                idx,
                "up" if idx % 2 else "down",
                (idx - 1) * 10,
                idx * 10,
                110.0 + (idx % 3),
                100.0 + (idx % 2),
            )
            for idx in range(1, 11)
        ]

        zhongshus = SegmentDetector(bis=[], include_expansion=True).detect_zhongshus(segments)

        parent = next(z for z in zhongshus if z.status == "expanded")
        self.assertEqual(parent.structure_count, 9)
        self.assertEqual(parent.end, segments[8].end)
        self.assertNotIn(segments[9].id, parent.xiang_ids)

    def test_detect_zhongshus_outer_ranges_create_higher_level_parent(self):
        segments = [
            self._segment(1, "up", 0, 10, 130.0, 100.0),
            self._segment(2, "down", 11, 20, 108.0, 102.0),
            self._segment(3, "up", 21, 30, 109.0, 103.0),
            self._segment(4, "down", 31, 40, 125.0, 115.0),
            self._segment(5, "up", 41, 50, 128.0, 116.0),
            self._segment(6, "down", 51, 60, 126.0, 120.0),
        ]

        zhongshus = SegmentDetector(bis=[], include_expansion=True).detect_zhongshus(segments)

        self.assertEqual(len(zhongshus), 3)
        parent = next(z for z in zhongshus if z.status == "expanded")
        self.assertEqual(parent.expansion_type, "center_overlap")
        self.assertEqual(parent.child_ids, ["zs_1", "zs_2"])
        self.assertAlmostEqual(parent.range_low, 115.0)
        self.assertAlmostEqual(parent.range_high, 128.0)

    def test_center_overlap_allows_shared_boundary_timestamp(self):
        bases = [
            Zhongshu(
                id="zs_1",
                start=self.t0,
                end=self.t0 + timedelta(minutes=10),
                range_high=11.0,
                range_low=10.0,
                zg=11.0,
                zd=10.0,
                gg=13.0,
                dd=9.0,
                xiang_ids=["x1", "x2", "x3"],
                level=1,
                source_type="bi",
                status="completed",
            ),
            Zhongshu(
                id="zs_2",
                start=self.t0 + timedelta(minutes=10),
                end=self.t0 + timedelta(minutes=20),
                range_high=14.0,
                range_low=12.0,
                zg=14.0,
                zd=12.0,
                gg=15.0,
                dd=11.5,
                xiang_ids=["x4", "x5", "x6"],
                level=1,
                source_type="bi",
                status="forming",
            ),
        ]

        parents = SegmentDetector(bis=[])._detect_expanded_zhongshus(
            bases, id_prefix="zs"
        )

        self.assertEqual(len(parents), 1)
        self.assertEqual(parents[0].expansion_type, "center_overlap")

    def test_overlapping_center_cores_remain_same_level_extension(self):
        bases = [
            Zhongshu(
                id="zs_1",
                start=self.t0,
                end=self.t0 + timedelta(minutes=10),
                range_high=11.0,
                range_low=10.0,
                zg=11.0,
                zd=10.0,
                gg=12.0,
                dd=9.0,
                xiang_ids=["x1", "x2", "x3"],
                level=1,
                source_type="bi",
                status="completed",
            ),
            Zhongshu(
                id="zs_2",
                start=self.t0 + timedelta(minutes=20),
                end=self.t0 + timedelta(minutes=30),
                range_high=10.8,
                range_low=10.2,
                zg=10.8,
                zd=10.2,
                gg=11.5,
                dd=9.5,
                xiang_ids=["x4", "x5", "x6"],
                level=1,
                source_type="bi",
                status="forming",
            ),
        ]

        parents = SegmentDetector(bis=[])._detect_expanded_zhongshus(
            bases, id_prefix="zs"
        )

        self.assertEqual(parents, [])
        self.assertTrue(all(z.parent_id is None for z in bases))

    def test_separated_outer_ranges_are_same_level_trend_not_expansion(self):
        bases = [
            Zhongshu(
                id="zs_1",
                start=self.t0,
                end=self.t0 + timedelta(minutes=10),
                range_high=11.0,
                range_low=10.0,
                zg=11.0,
                zd=10.0,
                gg=11.5,
                dd=9.5,
                xiang_ids=["x1", "x2", "x3"],
                level=1,
                source_type="bi",
                status="completed",
            ),
            Zhongshu(
                id="zs_2",
                start=self.t0 + timedelta(minutes=20),
                end=self.t0 + timedelta(minutes=30),
                range_high=14.0,
                range_low=13.0,
                zg=14.0,
                zd=13.0,
                gg=14.5,
                dd=12.0,
                xiang_ids=["x4", "x5", "x6"],
                level=1,
                source_type="bi",
                status="forming",
            ),
        ]

        parents = SegmentDetector(bis=[])._detect_expanded_zhongshus(
            bases, id_prefix="zs"
        )

        self.assertEqual(parents, [])
        self.assertTrue(all(z.parent_id is None for z in bases))

    def test_expanded_parents_do_not_share_the_same_child_center(self):
        bases = [
            Zhongshu(
                id=f"zs_{i + 1}",
                start=self.t0 + timedelta(minutes=i * 20),
                end=self.t0 + timedelta(minutes=i * 20 + 10),
                range_high=high,
                range_low=low,
                zg=high,
                zd=low,
                gg=gg,
                dd=dd,
                xiang_ids=[f"x_{i}_1", f"x_{i}_2", f"x_{i}_3"],
                level=1,
                source_type="bi",
                status="completed",
                structure_count=3,
            )
            for i, (high, low, gg, dd) in enumerate([
                (11.19, 11.08, 11.35, 10.42),
                (10.38, 10.18, 10.91, 9.99),
                (10.93, 10.72, 11.18, 10.40),
                (11.18, 11.18, 11.75, 11.03),
            ])
        ]

        parents = SegmentDetector(bis=[])._detect_expanded_zhongshus(
            bases, id_prefix="zs"
        )
        overlap_parents = [p for p in parents if p.expansion_type == "center_overlap"]
        child_ids = [child_id for p in overlap_parents for child_id in p.child_ids]

        self.assertEqual(len(overlap_parents), 2)
        self.assertEqual(len(child_ids), len(set(child_ids)))
        self.assertTrue(all(z.parent_id is not None for z in bases))

    def test_all_overlap_mode_preserves_legacy_shrinking_algorithm(self):
        segments = [
            self._segment(1, "up", 0, 10, 110.0, 100.0),
            self._segment(2, "down", 11, 20, 108.0, 102.0),
            self._segment(3, "up", 21, 30, 109.0, 103.0),
            self._segment(4, "down", 31, 40, 120.0, 105.0),
        ]

        zhongshus = SegmentDetector(bis=[], zhongshu_mode="all_overlap").detect_zhongshus(segments)

        self.assertEqual(len(zhongshus), 1)
        self.assertAlmostEqual(zhongshus[0].range_high, 108.0)
        self.assertAlmostEqual(zhongshus[0].range_low, 105.0)

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
