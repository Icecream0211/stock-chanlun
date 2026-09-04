"""
笔检测器 — 基于分型识别笔

贡献者：原作者 · claudecode（2026-08-31 修复笔不相接/方向不交替、min_bars 计数对象错误）
"""
from typing import Literal

import numpy as np
import pandas as pd

from .elements import Bi, KLineInclusion
from .fenxing_detector import Fenxing, FenxingDetector

BiMode = Literal["new", "old", "simple", "fractal"]


class BiDetector:
    """
    笔规则:
    1. 顶分型 + 底分型 = 一笔（向上笔: 底→顶，向下笔: 顶→底）
    2. 默认新笔：顶底分型不共用缠论K线，且极值间至少5根原始K线
    3. 同级别笔由连续顶底分型构成
    4. old/simple/fractal 为兼容模式，不与默认规则混算
    """

    def __init__(
        self,
        klines: pd.DataFrame,
        *,
        bi_mode: BiMode = "new",
        strict_price: bool = True,
        end_must_be_peak: bool = True,
    ):
        if bi_mode not in ("new", "old", "simple", "fractal"):
            raise ValueError(f"unsupported bi_mode: {bi_mode}")
        self.klines = klines.reset_index(drop=True)
        self._date_values = self.klines["date"].values
        self._fenxing_detector = FenxingDetector(klines)
        self._fenxings: list[Fenxing] = []
        self.bi_mode: BiMode = bi_mode
        self.strict_price = strict_price
        self.end_must_be_peak = end_must_be_peak

    @property
    def processed_klines(self) -> pd.DataFrame:
        """包含关系处理后的 K 线（与笔/分型检测一致）。"""
        return self._fenxing_detector.klines

    @property
    def inclusions(self) -> list[KLineInclusion]:
        """返回发生过合并的原始 K 线区间，供图表做紧凑提示。"""
        groups: list[KLineInclusion] = []
        for row in self.processed_klines.itertuples(index=False):
            raw_start = int(getattr(row, "raw_start_idx", 0))
            raw_end = int(getattr(row, "raw_end_idx", raw_start))
            direction = getattr(row, "inclusion_direction", None)
            if raw_end <= raw_start or direction not in ("up", "down"):
                continue
            groups.append(KLineInclusion(
                start=self.klines.iloc[raw_start]["date"],
                end=self.klines.iloc[raw_end]["date"],
                merged_date=row.date,
                direction=direction,
                count=raw_end - raw_start + 1,
                high=float(row.high),
                low=float(row.low),
                high_date=row.high_date,
                low_date=row.low_date,
            ))
        return groups

    @staticmethod
    def compress_fenxings(fenxings: list[Fenxing]) -> list[Fenxing]:
        """
        压缩分型序列：连续同类型分型仅保留更“极值”的那个。
        - 连续 top：保留 high 更高者
        - 连续 bottom：保留 low 更低者
        """
        if not fenxings:
            return []

        out: list[Fenxing] = [fenxings[0]]
        for fx in fenxings[1:]:
            last = out[-1]
            if fx.type != last.type:
                out.append(fx)
                continue

            if fx.type == "top":
                if fx.high > last.high:
                    out[-1] = fx
            else:  # bottom
                if fx.low < last.low:
                    out[-1] = fx

        return out

    def detect(self, min_bars: int = 5, include_virtual: bool = False) -> list[Bi]:
        """
        检测所有笔
        min_bars: 新笔/简单笔按原始K线数，旧笔按包含处理后K线数；标准最小值均为5。
        include_virtual: 是否在确认笔末尾附加一条未确认虚拟笔，供图表展示当前走势。
          虚拟笔不改变严格成笔条件，只能用于未确认尾段，不能确认中枢、买卖点或趋势。

        规则口径：
        - new：处理后分型不共用K线，极值之间至少5根原始K线；
        - old：包含处理后至少5根K线，顶底间有一根独立K线；
        - simple/fractal：仅用于兼容外部画法，不作为默认标准。
        所有模式都保持确认笔首尾相接、方向交替；不合格反向分型不会消耗起点。
        """
        self._fenxings = self._fenxing_detector.detect()
        if len(self._fenxings) < 2:
            return []

        # 单次状态扫描：不预先删除分型，避免间距判断前丢失候选端点。
        seq: list[Fenxing] = [self._fenxings[0]]
        for fx in self._fenxings[1:]:
            last = seq[-1]
            if fx.type == last.type:
                # 同型只在严格创新高/低时后移；同价保留最早端点。
                if self._is_more_extreme(fx, last):
                    seq[-1] = fx
                continue
            if self._can_make_bi(last, fx, min_bars=min_bars):
                seq.append(fx)
            # 不成笔时不消耗 last；后续同型极值仍可延伸上一确认端点。

        bis: list[Bi] = []
        for a, b in zip(seq, seq[1:]):
            bis.append(self._build_bi(a, b, len(bis) + 1))
        if include_virtual and seq:
            bis.extend(self._build_virtual_tail(seq[-1], len(bis) + 1))
        return bis

    @staticmethod
    def _is_more_extreme(candidate: Fenxing, current: Fenxing) -> bool:
        if candidate.type == "top":
            return candidate.high > current.high
        return candidate.low < current.low

    def _can_make_bi(self, start: Fenxing, end: Fenxing, *, min_bars: int) -> bool:
        if start.type == end.type or end.index <= start.index:
            return False
        if not self._satisfies_span(start, end, min_bars=min_bars):
            return False
        if self.strict_price and not self._has_valid_price_direction(start, end):
            return False
        return not self.end_must_be_peak or self._end_is_peak(start, end)

    def _satisfies_span(self, start: Fenxing, end: Fenxing, *, min_bars: int) -> bool:
        processed_gap = end.index - start.index
        raw_start = self._raw_index(start)
        raw_end = self._raw_index(end)
        if raw_end <= raw_start:
            return False
        raw_count = raw_end - raw_start + 1
        required = max(5, int(min_bars))

        if self.bi_mode == "old":
            # 分型中心相隔4根缠论K线，保证两分型间有一根独立K线。
            return processed_gap >= max(4, required - 1)
        if self.bi_mode == "new":
            # 中心相隔3保证三K分型不共用缠论K线；根数按原始极值K线计算。
            return processed_gap >= 3 and raw_count >= required
        if self.bi_mode == "simple":
            return raw_count >= required
        return True

    @staticmethod
    def _has_valid_price_direction(start: Fenxing, end: Fenxing) -> bool:
        if start.type == "bottom":
            return float(end.high) > float(start.low)
        return float(end.low) < float(start.high)

    def _end_is_peak(self, start: Fenxing, end: Fenxing) -> bool:
        window = self.processed_klines.iloc[start.index:end.index + 1]
        if window.empty:
            return False
        if start.type == "bottom":
            return float(end.high) >= float(window["high"].max()) - 1e-8
        return float(end.low) <= float(window["low"].min()) + 1e-8

    def _raw_index(self, fx: Fenxing) -> int:
        if fx.raw_index is not None:
            return int(fx.raw_index)
        target = np.datetime64(fx.date)
        idx = int(np.searchsorted(self._date_values, target, side="left"))
        return min(max(idx, 0), max(0, len(self._date_values) - 1))

    def _build_bi(self, start: Fenxing, end: Fenxing, number: int) -> Bi:
        if start.type == "bottom":
            return Bi(
                id=f"bi_up_{number}",
                start=start.date,
                end=end.date,
                direction="up",
                high=float(end.high),
                low=float(start.low),
                start_price=float(start.low),
                end_price=float(end.high),
                rule=self.bi_mode,
            )
        return Bi(
            id=f"bi_down_{number}",
            start=start.date,
            end=end.date,
            direction="down",
            high=float(start.high),
            low=float(end.low),
            start_price=float(start.high),
            end_price=float(end.low),
            rule=self.bi_mode,
        )

    def _build_virtual_tail(self, start: Fenxing, number: int) -> list[Bi]:
        """
        从最后确认端点连接到当前反向极值，只绘制一根未确认候选笔。

        被间距、价格或终点极值规则拒绝的中间分型不再串成多根“伪笔”；候选笔
        会随行情重算，并在反向分型满足当前模式后替换为正式笔。
        """
        processed = self.processed_klines
        tail = processed.iloc[start.index + 1:]
        if tail.empty:
            return []

        if start.type == "bottom":
            idx = int(tail["high"].astype(float).idxmax())
            row = processed.loc[idx]
            end_price = float(row["high"])
            if end_price <= float(start.low):
                return []
            end_date = row.get("high_date", row["date"])
            direction = "up"
            start_price = float(start.low)
        else:
            idx = int(tail["low"].astype(float).idxmin())
            row = processed.loc[idx]
            end_price = float(row["low"])
            if end_price >= float(start.high):
                return []
            end_date = row.get("low_date", row["date"])
            direction = "down"
            start_price = float(start.high)

        if hasattr(end_date, "to_pydatetime"):
            end_date = end_date.to_pydatetime()
        return [Bi(
            id=f"bi_virtual_{number}",
            start=start.date,
            end=end_date,
            direction=direction,
            high=max(start_price, end_price),
            low=min(start_price, end_price),
            start_price=start_price,
            end_price=end_price,
            confirmed=False,
            rule="virtual",
        )]
