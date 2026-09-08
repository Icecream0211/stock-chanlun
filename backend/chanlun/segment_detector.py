"""
线段与中枢检测器
"""
from typing import Literal, Optional

from .elements import Bi, XiangSegment, Zhongshu


class SegmentDetector:
    """
    线段规则:
    - 笔必须首尾相接且方向交替
    - 至少3笔构成线段；同向端点形成局部极值时确认线段结束
    - 相邻线段共享同一个转折端点

    中枢规则（standard 模式）:
    - 3个连续、方向交替的已完成同级结构存在交集时形成中枢
    - 初始三结构确定固定核心 [ZD, ZG]，后续延伸不收窄核心
    - 后续结构与固定核心仍有严格价格交集时，属于中枢延伸
    - 首条价格区间与核心完全无交集的结构，即结束旧中枢，并作为新中枢的搜索起点
    - 九结构/外围重叠的递归父中枢只在显式研究模式中生成，不作为默认图层
    """

    def __init__(
        self,
        bis: list[Bi],
        *,
        zhongshu_mode: Literal["standard", "all_overlap"] = "standard",
        price_epsilon: float = 1e-8,
        include_expansion: bool = False,
    ):
        self.bis = bis
        self.zhongshu_mode = zhongshu_mode
        self.price_epsilon = max(0.0, float(price_epsilon))
        self.include_expansion = include_expansion

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
            run_start_count = len(segments)
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
                    start = end + 1
                    break
                # 下一线段从当前线段终点发出的反向笔开始，二者共享端点。
                start = end + 1

            # 已经出现过确认线段后，即使尾部只剩 1~2 笔，也画成未确认尾线段。
            # 这条线段只供显示，避免相邻线段之间出现空白；确认计算仍由调用方过滤。
            if len(segments) > run_start_count and start < len(run):
                tail = run[start:]
                segments.append(self._build_segment(tail, len(segments) + 1, False))

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
            # 虚拟笔只能延伸未确认尾段，不能反过来确认正式线段。
            if not all(getattr(b, "confirmed", True) for b in run[start:candidate + 3]):
                continue
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
            confirmed=confirmed and all(getattr(b, "confirmed", True) for b in group),
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

    def detect_same_level_bi_zhongshus(
        self,
        segments: Optional[list[XiangSegment]] = None,
    ) -> list[Zhongshu]:
        """按线段边界分解笔中枢。

        同级别分解不能把整段历史的笔机械按每三笔切块：那样会让一个笔
        中枢穿过已经完成的线段转折，误显示成仍在延伸的“大中枢”。传入
        线段后，每个线段只使用其内部的笔独立运行中枢状态机；相邻线段
        的笔不允许共同组成中枢。未确认尾段仅在最后三笔（含虚拟笔）确有
        三笔重叠时，给出 ``confirmed=False`` 的候选中枢。

        ``segments=None`` 保留旧调用的三笔分组行为，兼容旧接口与历史数据。
        引擎始终传入线段，因此图表默认使用严格的线段边界口径。
        """
        if segments is None:
            return self._detect_legacy_same_level_bi_zhongshus()

        bi_by_id = {bi.id: bi for bi in self.bis}
        zhongshus: list[Zhongshu] = []

        def append_local(items: list[Zhongshu], segment: XiangSegment) -> None:
            for item in items:
                zhongshus.append(item.model_copy(update={
                    "id": f"bi_same_level_{len(zhongshus) + 1}",
                    "decomposition": "same_level",
                }))

        for segment in segments:
            segment_bis = [bi_by_id[bi_id] for bi_id in segment.bi_ids if bi_id in bi_by_id]
            if len(segment_bis) < 3:
                continue
            if segment.confirmed:
                # 只产生子中枢，不在单个线段内部递归生成父中枢；父级中枢
                # 应由下一层线段序列另行识别，不能跨当前边界拼接。
                append_local(
                    self._detect_standard_zhongshus(
                        segment_bis,
                        source_type="bi",
                        level=1,
                        id_prefix="scoped_bi_zs",
                    ),
                    segment,
                )
                continue

            # 未确认尾段：只能以末尾三笔（至少有一笔虚拟）形成候选，不能
            # 用已完成的前序笔重新拼出一个“已确认”中枢。
            tail = segment_bis[-3:]
            if (
                len(tail) == 3
                and any(not getattr(bi, "confirmed", True) for bi in tail)
                and tail[0].direction != tail[1].direction
                and tail[0].direction == tail[2].direction
            ):
                zg = float(min(bi.high for bi in tail))
                zd = float(max(bi.low for bi in tail))
                if self._has_overlap(zg, zd):
                    zhongshus.append(Zhongshu(
                        id=f"bi_same_level_{len(zhongshus) + 1}",
                        start=tail[0].start,
                        end=tail[-1].end,
                        range_high=zg,
                        range_low=zd,
                        zg=zg,
                        zd=zd,
                        gg=float(max(bi.high for bi in tail)),
                        dd=float(min(bi.low for bi in tail)),
                        xiang_ids=[bi.id for bi in tail],
                        level=1,
                        confirmed=False,
                        source_type="bi",
                        status="forming",
                        structure_count=3,
                        decomposition="same_level",
                    ))
        return zhongshus

    def _detect_legacy_same_level_bi_zhongshus(self) -> list[Zhongshu]:
        """旧的三笔分块口径，仅供兼容未提供线段的调用方。"""
        zhongshus: list[Zhongshu] = []
        for start_idx in range(0, len(self.bis) - 2, 3):
            group = self.bis[start_idx:start_idx + 3]
            if not self._is_alternating_triplet(group):
                continue
            zg = float(min(item.high for item in group))
            zd = float(max(item.low for item in group))
            if not self._has_overlap(zg, zd):
                continue
            zhongshus.append(Zhongshu(
                id=f"bi_same_level_{len(zhongshus) + 1}",
                start=group[0].start,
                end=group[-1].end,
                range_high=zg,
                range_low=zd,
                zg=zg,
                zd=zd,
                gg=float(max(item.high for item in group)),
                dd=float(min(item.low for item in group)),
                xiang_ids=[item.id for item in group],
                level=1,
                confirmed=True,
                source_type="bi",
                status="forming",
                structure_count=3,
                decomposition="same_level",
            ))
        return zhongshus

    def _detect_structure_zhongshus(
        self,
        structures: list[Bi] | list[XiangSegment],
        *,
        source_type: Literal["bi", "segment"],
        level: int,
        id_prefix: str,
    ) -> list[Zhongshu]:
        """按选定模式识别中枢；默认使用固定核心的标准模式。"""
        if len(structures) < 3:
            return []

        if self.zhongshu_mode == "all_overlap":
            return self._detect_all_overlap_zhongshus(
                structures,
                source_type=source_type,
                level=level,
                id_prefix=id_prefix,
            )

        base = self._detect_standard_zhongshus(
            structures,
            source_type=source_type,
            level=level,
            id_prefix=id_prefix,
        )
        if not self.include_expansion:
            return base
        expanded = self._detect_expanded_zhongshus(
            base,
            id_prefix=id_prefix,
            structures=structures,
        )
        return sorted([*base, *expanded], key=lambda z: (z.end, z.level, z.start))

    def _detect_standard_zhongshus(
        self,
        structures: list[Bi] | list[XiangSegment],
        *,
        source_type: Literal["bi", "segment"],
        level: int,
        id_prefix: str,
    ) -> list[Zhongshu]:
        """
        标准中枢状态机。

        初始三结构确定固定核心 [ZD, ZG]，且必须满足严格的 ZG > ZD。
        后续结构只要价格区间与固定核心仍有严格交集，均为延伸，核心本身
        不收窄、不平移。第一条价格区间完全脱离核心的结构立即结束旧中枢；
        该离开结构不属于旧中枢，并从它重新开始搜索下一中枢。
        """
        zhongshus: list[Zhongshu] = []
        i = 0

        while i <= len(structures) - 3:
            group = structures[i:i + 3]
            if not self._is_alternating_triplet(group):
                i += 1
                continue

            zg = float(min(s.high for s in group))
            zd = float(max(s.low for s in group))
            if not self._has_overlap(zg, zd):
                i += 1
                continue

            included = list(group)
            cursor = i + 3
            completed = False
            exit_direction = None

            while cursor < len(structures):
                current = structures[cursor]
                if self._intersects_core(current, zd, zg):
                    included.append(current)
                    cursor += 1
                    continue

                # 完全脱离的当前结构就是中枢结束证据，不能等待下一结构“确认”。
                completed = True
                exit_direction = self._outside_direction(current, zd, zg)
                break

            structure_count = len(included)
            status = "completed" if completed else ("extended" if structure_count > 3 else "forming")
            zhongshus.append(Zhongshu(
                id=f"{id_prefix}_{len(zhongshus) + 1}",
                start=group[0].start,
                end=included[-1].end,
                range_high=zg,
                range_low=zd,
                zg=zg,
                zd=zd,
                gg=float(max(s.high for s in included)),
                dd=float(min(s.low for s in included)),
                xiang_ids=[s.id for s in included],
                level=level,
                confirmed=all(getattr(s, "confirmed", True) for s in group),
                source_type=source_type,
                status=status,
                structure_count=structure_count,
                extension_count=max(0, structure_count - 3),
                exit_direction=exit_direction,
            ))

            # 从离开结构重新寻找下一中枢；未离开说明已经扫描到序列尾部。
            i = cursor if completed else len(structures)

        return zhongshus

    def _detect_all_overlap_zhongshus(
        self,
        structures: list[Bi] | list[XiangSegment],
        *,
        source_type: Literal["bi", "segment"],
        level: int,
        id_prefix: str,
    ) -> list[Zhongshu]:
        """兼容旧版“所有已纳入结构持续求交集”的工程模式。"""

        zhongshus: list[Zhongshu] = []
        i = 0

        while i <= len(structures) - 3:
            group = structures[i:i + 3]

            # 计算三段重叠区间
            range_high = min(s.high for s in group)
            range_low = max(s.low for s in group)

            if self._has_overlap(range_high, range_low):
                # 重叠 → 形成中枢，尝试向后延伸
                cur_start = group[0].start
                cur_end = group[-1].end
                xiang_ids = [s.id for s in group]
                extend_idx = i + 3

                while extend_idx < len(structures):
                    nxt = structures[extend_idx]
                    # 新段与当前中枢重叠 → 并入；中枢区间取所有段的交叠（收窄），而非并集
                    if self._intersects_core(nxt, range_low, range_high):
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
                    zg=float(range_high),
                    zd=float(range_low),
                    gg=float(max(s.high for s in structures[i:extend_idx])),
                    dd=float(min(s.low for s in structures[i:extend_idx])),
                    xiang_ids=xiang_ids,
                    level=level,
                    confirmed=all(getattr(s, "confirmed", True) for s in structures[i:extend_idx]),
                    source_type=source_type,
                    status="extended" if len(xiang_ids) > 3 else "forming",
                    structure_count=len(xiang_ids),
                    extension_count=max(0, len(xiang_ids) - 3),
                ))
                i = extend_idx  # 跳到中枢结束后的第一个线段
            else:
                i += 1

        return zhongshus

    def _detect_expanded_zhongshus(
        self,
        base: list[Zhongshu],
        *,
        id_prefix: str,
        structures: Optional[list[Bi] | list[XiangSegment]] = None,
    ) -> list[Zhongshu]:
        """根据九结构递归和相邻同级中枢外围重叠生成高一级父中枢。

        九结构升级不能只看数量：必须把 S1..S9 固定分为 3+3+3，使用
        三个组合走势的完整波动区间重新求交集。两个同级中枢升级则要求
        核心区间已经分离、但外围波动区间仍有重叠；核心重叠属于延伸，
        外围也分离属于同级趋势延续。
        """
        expanded: list[Zhongshu] = []
        structure_by_id = {s.id: s for s in structures or []}

        for child in base:
            if child.structure_count < 9:
                continue
            child_structures = [
                structure_by_id[structure_id]
                for structure_id in child.xiang_ids
                if structure_id in structure_by_id
            ]
            complete_count = len(child_structures) // 3 * 3
            if complete_count < 9:
                continue

            grouped: list[dict] = []
            for offset in range(0, complete_count, 3):
                triplet = child_structures[offset:offset + 3]
                if not self._is_alternating_triplet(triplet):
                    break
                grouped.append({
                    "start": triplet[0].start,
                    "end": triplet[-1].end,
                    "high": float(max(s.high for s in triplet)),
                    "low": float(min(s.low for s in triplet)),
                    "structures": triplet,
                })
            if len(grouped) < 3:
                continue

            initial_groups = grouped[:3]
            parent_zg = float(min(group["high"] for group in initial_groups))
            parent_zd = float(max(group["low"] for group in initial_groups))
            if not self._has_overlap(parent_zg, parent_zd):
                continue

            included_groups = list(initial_groups)
            cursor = 3
            while cursor < len(grouped):
                current = grouped[cursor]
                if self._range_intersects_core(
                    current["low"], current["high"], parent_zd, parent_zg
                ):
                    included_groups.append(current)
                    cursor += 1
                    continue

                # 与基础中枢一致：高一级走势离开后，下一反向走势重新进入
                # 固定核心，仍算高一级中枢延伸；否则父中枢在离开前结束。
                if cursor + 1 >= len(grouped):
                    break
                pullback = grouped[cursor + 1]
                if self._range_intersects_core(
                    pullback["low"], pullback["high"], parent_zd, parent_zg
                ):
                    included_groups.extend([current, pullback])
                    cursor += 2
                    continue
                break

            included_structures = [
                structure
                for group in included_groups
                for structure in group["structures"]
            ]
            parent = Zhongshu(
                id=f"{id_prefix}_expanded_{len(expanded) + 1}",
                start=included_structures[0].start,
                end=included_structures[-1].end,
                range_high=parent_zg,
                range_low=parent_zd,
                zg=parent_zg,
                zd=parent_zd,
                gg=float(max(s.high for s in included_structures)),
                dd=float(min(s.low for s in included_structures)),
                xiang_ids=[s.id for s in included_structures],
                level=child.level + 1,
                confirmed=all(getattr(s, "confirmed", True) for s in included_structures),
                source_type=child.source_type,
                status="expanded",
                structure_count=len(included_structures),
                extension_count=max(0, len(included_groups) - 3),
                expansion_type="nine_structure",
                child_ids=[child.id],
            )
            child.parent_id = parent.id
            expanded.append(parent)

        for left, right in zip(base, base[1:]):
            # 同一个基础中枢只能归属于一个直接父中枢。旧实现允许
            # A+B、B+C 同时生成两个父中枢，B 被重复挂载，图上会出现
            # 一串彼此覆盖的“扩展”标记，也破坏了层级树的一致性。
            if left.parent_id is not None or right.parent_id is not None:
                continue
            if (
                left.level != right.level
                or left.source_type != right.source_type
                or not left.confirmed
                or not right.confirmed
                # 相邻走势通常共享同一个转折时刻；只有真正时间倒序才非法。
                or left.end > right.start
                or set(left.xiang_ids).intersection(right.xiang_ids)
            ):
                continue
            left_gg = left.gg if left.gg is not None else left.range_high
            left_dd = left.dd if left.dd is not None else left.range_low
            right_gg = right.gg if right.gg is not None else right.range_high
            right_dd = right.dd if right.dd is not None else right.range_low
            left_zg = left.zg if left.zg is not None else left.range_high
            left_zd = left.zd if left.zd is not None else left.range_low
            right_zg = right.zg if right.zg is not None else right.range_high
            right_zd = right.zd if right.zd is not None else right.range_low

            # 同级上涨：后中枢核心在上；外围仍重叠才升级，外围完全分离
            # (DD2 > GG1) 则是同级上涨趋势延续。下跌方向对称。
            right_is_above = right_zd > left_zg + self.price_epsilon
            right_is_below = right_zg < left_zd - self.price_epsilon
            if not (right_is_above or right_is_below):
                # 两核心仍重叠，不能把原中枢延伸误标为高一级扩张。
                continue
            if right_is_above and right_dd > left_gg + self.price_epsilon:
                continue
            if right_is_below and right_gg < left_dd - self.price_epsilon:
                continue

            parent_zg = float(min(left_gg, right_gg))
            parent_zd = float(max(left_dd, right_dd))
            if not self._has_overlap(parent_zg, parent_zd):
                continue

            parent = Zhongshu(
                id=f"{id_prefix}_expanded_{len(expanded) + 1}",
                start=left.start,
                end=right.end,
                range_high=parent_zg,
                range_low=parent_zd,
                zg=parent_zg,
                zd=parent_zd,
                gg=float(max(left_gg, right_gg)),
                dd=float(min(left_dd, right_dd)),
                xiang_ids=list(dict.fromkeys([*left.xiang_ids, *right.xiang_ids])),
                level=max(left.level, right.level) + 1,
                confirmed=left.confirmed and right.confirmed,
                source_type=left.source_type,
                status="expanded",
                structure_count=left.structure_count + right.structure_count,
                extension_count=left.extension_count + right.extension_count,
                expansion_type="center_overlap",
                child_ids=[left.id, right.id],
            )
            left.parent_id = parent.id
            right.parent_id = parent.id
            expanded.append(parent)

        return expanded

    def _has_overlap(self, high: float, low: float) -> bool:
        """中枢核心必须是具有宽度的严格交集，ZG == ZD 不构成中枢。"""
        return float(high) - float(low) > self.price_epsilon

    def _intersects_core(self, structure: Bi | XiangSegment, zd: float, zg: float) -> bool:
        return self._range_intersects_core(structure.low, structure.high, zd, zg)

    def _range_intersects_core(
        self,
        low: float,
        high: float,
        zd: float,
        zg: float,
    ) -> bool:
        return min(float(high), float(zg)) - max(float(low), float(zd)) > self.price_epsilon

    @staticmethod
    def _is_alternating_triplet(group: list[Bi] | list[XiangSegment]) -> bool:
        return (
            len(group) == 3
            and group[0].direction != group[1].direction
            and group[0].direction == group[2].direction
            and all(getattr(s, "confirmed", True) for s in group)
        )

    @staticmethod
    def _outside_direction(
        structure: Bi | XiangSegment,
        zd: float,
        zg: float,
    ) -> Optional[Literal["up", "down"]]:
        if structure.low > zg:
            return "up"
        if structure.high < zd:
            return "down"
        return None

    @staticmethod
    def _point_outside_direction(
        price: float,
        zd: float,
        zg: float,
    ) -> Optional[Literal["up", "down"]]:
        if price > zg:
            return "up"
        if price < zd:
            return "down"
        return None

    def get_zhongshu_for_price(self, zhongshus: list[Zhongshu],
                                 price: float) -> Optional[Zhongshu]:
        """找到价格所在的中枢"""
        for zs in reversed(zhongshus):
            if zs.range_low <= price <= zs.range_high:
                return zs
        return None
