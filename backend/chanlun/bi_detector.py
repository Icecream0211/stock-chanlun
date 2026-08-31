"""
笔检测器 — 基于分型识别笔

贡献者：原作者 · claudecode（2026-08-31 修复笔不相接/方向不交替、min_bars 计数对象错误）
"""
import numpy as np
import pandas as pd
from typing import Optional
from datetime import datetime
from .elements import Bi
from .fenxing_detector import FenxingDetector, Fenxing


class BiDetector:
    """
    笔规则:
    1. 顶分型 + 底分型 = 一笔（向上笔: 底→顶，向下笔: 顶→底）
    2. 笔至少需要5根K线（含分型）
    3. 同级别笔由连续顶底分型构成
    """

    def __init__(self, klines: pd.DataFrame):
        self.klines = klines.reset_index(drop=True)
        self._date_values = self.klines["date"].values
        self._fenxing_detector = FenxingDetector(klines)
        self._fenxings: list[Fenxing] = []

    @property
    def processed_klines(self) -> pd.DataFrame:
        """包含关系处理后的 K 线（与笔/分型检测一致）。"""
        return self._fenxing_detector.klines

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
                if fx.high >= last.high:
                    out[-1] = fx
            else:  # bottom
                if fx.low <= last.low:
                    out[-1] = fx

        return out

    def detect(self, min_bars: int = 5) -> list[Bi]:
        """
        检测所有笔
        min_bars: 笔最少K线数（默认5根，按【包含处理后】序列计数）

        --- claudecode 2026-08-31 重写，修复两个结构性缺陷 ---

        缺陷①【笔不首尾相接、方向不交替】
          原实现逐对扫描分型，`if bar_count >= min_bars` 不满足时**跳过该对但
          仍 i += 1**，等于把 fx1 也消耗掉了。实测 002202 日线：270 个分型中
          190 对因K线数不足被跳过，导致 79 笔里出现 60 处断点、37 对同向相邻笔
          （连续四根 down 的情况都有）。而缠论的笔必须首尾相接、方向交替、
          无缝覆盖走势。
          修法：先构造【已确认端点序列】，间隔不足时**忽略该分型、保留前一个端点**
          （不消耗 last），再由相邻端点成笔 —— 首尾相接与方向交替由构造天然保证。

        缺陷②【min_bars 数错了对象】
          原用 `_count_klines_between` 数**原始K线**，但分型来自**包含处理后**
          的序列。分钟级别包含合并率达 40~43%（日线仅 27%），5 根原始K线在
          5 分钟级别可能只对应 2~3 根处理后K线，远不足以成笔 —— 这是
          "30分/5分比日线错得更离谱"的直接原因。
          修法：改用 Fenxing.index（本就是处理后序列的下标）之差，
          min_bars=5 → 序号差 >= 4（顶底之间至少夹 1 根独立K线，标准缠论口径）。
        """
        self._fenxings = self.compress_fenxings(self._fenxing_detector.detect())
        if len(self._fenxings) < 2:
            return []

        min_gap = max(1, int(min_bars) - 1)

        # 第一步：构造已确认端点序列
        seq: list[Fenxing] = [self._fenxings[0]]
        for fx in self._fenxings[1:]:
            last = seq[-1]
            if fx.type == last.type:
                # 同型取更极端（compress_fenxings 已做，此处兜底）
                if (fx.type == "top" and fx.high >= last.high) or (
                    fx.type == "bottom" and fx.low <= last.low
                ):
                    seq[-1] = fx
                continue
            if fx.index - last.index >= min_gap:
                seq.append(fx)
            # else: 间隔不足 → 忽略该分型，保留 last（关键，勿改成 seq[-1] = fx）

        # 第二步：相邻端点成笔
        bis: list[Bi] = []
        for a, b in zip(seq, seq[1:]):
            if a.type == "bottom":
                bis.append(Bi(
                    id=f"bi_up_{len(bis)+1}",
                    start=a.date, end=b.date, direction="up",
                    high=float(b.high), low=float(a.low),
                    start_price=float(a.low), end_price=float(b.high),
                ))
            else:
                bis.append(Bi(
                    id=f"bi_down_{len(bis)+1}",
                    start=a.date, end=b.date, direction="down",
                    high=float(a.high), low=float(b.low),
                    start_price=float(a.high), end_price=float(b.low),
                ))
        return bis

    def _count_klines_between(self, start: datetime, end: datetime) -> int:
        """计算两个时间之间的K线数量（searchsorted，避免全表布尔掩码）"""
        dates = self._date_values
        # np.datetime64 显式转换：部分 numpy/pandas 版本组合下，datetime64 数组与裸
        # datetime/Timestamp 标量比较会抛 TypeError，需先转换为同类型再比较
        left = int(np.searchsorted(dates, np.datetime64(start), side="left"))
        right = int(np.searchsorted(dates, np.datetime64(end), side="right"))
        return max(0, right - left)
