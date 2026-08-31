"""
线段与中枢检测器
"""
from typing import Optional
from datetime import datetime
from .elements import Bi, XiangSegment, Zhongshu


class SegmentDetector:
    """
    线段规则:
    - 笔必须首尾相接且方向交替
    - 至少3笔构成线段；同向端点形成局部极值时确认线段结束
    - 相邻线段共享同一个转折端点

    中枢规则:
    - 3个（或以上）连续同级别线段的重叠区域构成中枢
    """

    def __init__(self, bis: list[Bi]):
        self.bis = bis

    def detect_segments(self, min_overlap_bis: int = 3, max_iterations: int = 10000) -> list[XiangSegment]:
        """
        从方向交替的笔序列识别线段。

        原实现按“三笔价格重叠”分块，并只允许同方向笔延伸；而合法笔序列天然
        上下交替，导致延伸条件永远难以成立。这里改为同向端点极值确认：例如
        上线段中，某根向上笔的终点高于前一向上笔、且高于后一向上笔，即形成
        已确认顶部。尾部不足以等待后一同向笔时仍返回未确认线段供图表展示。

        max_iterations 保留在签名中以兼容既有调用，不再需要循环保险。
        """
        del max_iterations
        min_bis = max(3, int(min_overlap_bis))
        if min_bis % 2 == 0:
            min_bis += 1

        segments: list[XiangSegment] = []
        for run in self._continuous_runs():
            start = 0
            while len(run) - start >= min_bis:
                end = self._find_confirmed_end(run, start, min_bis)
                confirmed = end is not None
                if end is None:
                    # 最后一笔必须与线段首笔同向，保证线段终点是同级转折点。
                    end = len(run) - 1
                    if (end - start) % 2:
                        end -= 1
                    if end - start + 1 < min_bis:
                        break

                group = run[start:end + 1]
                segments.append(self._build_segment(group, len(segments) + 1, confirmed))
                if not confirmed:
                    break
                # 下一线段从当前线段终点发出的反向笔开始，二者共享端点。
                start = end + 1

        return segments

    def _continuous_runs(self) -> list[list[Bi]]:
        """将异常的断点/同向笔隔离，避免一个脏点污染后续全部线段。"""
        if not self.bis:
            return []
        runs: list[list[Bi]] = [[self.bis[0]]]
        for bi in self.bis[1:]:
            prev = runs[-1][-1]
            connected = prev.end == bi.start and abs(prev.end_price - bi.start_price) <= 1e-8
            alternating = prev.direction != bi.direction
            if connected and alternating:
                runs[-1].append(bi)
            else:
                runs.append([bi])
        return runs

    @staticmethod
    def _find_confirmed_end(run: list[Bi], start: int, min_bis: int) -> Optional[int]:
        first = start + min_bis - 1
        direction = run[start].direction
        # 需要后一根同方向笔（candidate + 2）确认当前极值。
        for candidate in range(first, len(run) - 2, 2):
            previous_price = run[candidate - 2].end_price
            current_price = run[candidate].end_price
            next_price = run[candidate + 2].end_price
            if direction == "up":
                if current_price > previous_price and current_price >= next_price:
                    return candidate
            elif current_price < previous_price and current_price <= next_price:
                return candidate
        return None

    @staticmethod
    def _build_segment(group: list[Bi], number: int, confirmed: bool) -> XiangSegment:
        first, last = group[0], group[-1]
        return XiangSegment(
            id=f"xiang_{number}",
            start=first.start,
            end=last.end,
            direction=first.direction,
            high=max(b.high for b in group),
            low=min(b.low for b in group),
            start_price=first.start_price,
            end_price=last.end_price,
            bi_ids=[b.id for b in group],
            level=2,
            confirmed=confirmed,
        )

    def detect_zhongshus(self, segments: list[XiangSegment]) -> list[Zhongshu]:
        """检测线段中枢。"""
        return self._detect_structure_zhongshus(
            segments,
            source_type="segment",
            level=2,
            id_prefix="zs",
        )

    def detect_bi_zhongshus(self) -> list[Zhongshu]:
        """检测笔中枢：连续三笔价格区间存在交集时形成。"""
        return self._detect_structure_zhongshus(
            self.bis,
            source_type="bi",
            level=1,
            id_prefix="bi_zs",
        )

    def _detect_structure_zhongshus(
        self,
        structures: list[Bi] | list[XiangSegment],
        *,
        source_type: str,
        level: int,
        id_prefix: str,
    ) -> list[Zhongshu]:
        """
        通用中枢滑动窗口：
        遍历同级结构序列，每取得连续3个结构计算重叠区间：
        - 有重叠 → 构成中枢，尝试向后延伸（后续线段若与之重叠则并入）
        - 无重叠 → 跳过，继续寻找下一组
        相邻中枢之间不会重复使用同一个初始三结构窗口。
        """
        if len(structures) < 3:
            return []

        zhongshus: list[Zhongshu] = []
        i = 0

        while i <= len(structures) - 3:
            group = structures[i:i + 3]

            # 计算三段重叠区间
            range_high = min(s.high for s in group)
            range_low = max(s.low for s in group)

            if range_high > range_low:
                # 重叠 → 形成中枢，尝试向后延伸
                cur_start = group[0].start
                cur_end = group[-1].end
                xiang_ids = [s.id for s in group]
                extend_idx = i + 3

                while extend_idx < len(structures):
                    nxt = structures[extend_idx]
                    # 新段与当前中枢重叠 → 并入；中枢区间取所有段的交叠（收窄），而非并集
                    if nxt.high > range_low and nxt.low < range_high:
                        range_high = min(range_high, nxt.high)
                        range_low = max(range_low, nxt.low)
                        cur_end = nxt.end
                        xiang_ids.append(nxt.id)
                        extend_idx += 1
                    else:
                        break

                zhongshus.append(Zhongshu(
                    id=f"{id_prefix}_{len(zhongshus)+1}",
                    start=cur_start,
                    end=cur_end,
                    range_high=float(range_high),
                    range_low=float(range_low),
                    xiang_ids=xiang_ids,
                    level=level,
                    confirmed=all(getattr(s, "confirmed", True) for s in structures[i:extend_idx]),
                    source_type=source_type,
                ))
                i = extend_idx  # 跳到中枢结束后的第一个线段
            else:
                i += 1

        return zhongshus

    def get_zhongshu_for_price(self, zhongshus: list[Zhongshu],
                                 price: float) -> Optional[Zhongshu]:
        """找到价格所在的中枢"""
        for zs in reversed(zhongshus):
            if zs.range_low <= price <= zs.range_high:
                return zs
        return None
