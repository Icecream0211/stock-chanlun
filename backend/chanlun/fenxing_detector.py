"""Fenxing detector: top and bottom fractals after inclusion processing."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import numpy as np
import pandas as pd


@dataclass
class Fenxing:
    """A top or bottom fractal."""

    date: datetime
    type: Literal["top", "bottom"]
    high: float
    low: float
    index: int
    raw_index: int | None = None  # 分型极值所在的原始 K 线下标
    raw_start_idx: int | None = None  # 中间缠论 K 线覆盖的原始起点
    raw_end_idx: int | None = None  # 中间缠论 K 线覆盖的原始终点


class FenxingDetector:
    """
    Detect Chanlun fenxing.

    The detector first removes containing K-line relationships. In an upward
    merge, keep the higher high and higher low; in a downward merge, keep the
    lower high and lower low. This preserves the effective swing shape used by
    later bi detection.
    """

    def __init__(self, klines: pd.DataFrame):
        self.klines = klines.reset_index(drop=True)
        self._process_inclusion()

    def _process_inclusion(self):
        """Process containing K-lines before fenxing detection."""
        df = self.klines
        if df.empty:
            return

        highs = df["high"].to_numpy(dtype=float)
        lows = df["low"].to_numpy(dtype=float)
        opens = df["open"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)
        dates = df["date"].tolist()
        volumes = df["volume"].to_numpy(dtype=float) if "volume" in df.columns else np.zeros(len(df))

        out_high = [highs[0]]
        out_low = [lows[0]]
        out_open = [opens[0]]
        out_close = [closes[0]]
        out_date = [dates[0]]
        out_vol = [float(volumes[0])]
        out_raw_start = [0]
        out_raw_end = [0]
        out_high_raw = [0]
        out_low_raw = [0]
        out_inclusion_direction: list[str | None] = [None]

        def merge_direction(prev_h, prev_l, before_h, before_l, cur_h, cur_l) -> str:
            if len(out_high) >= 2:
                if prev_h >= before_h and prev_l >= before_l:
                    return "up"
                if prev_h <= before_h and prev_l <= before_l:
                    return "down"
            return "up" if cur_h >= prev_h and cur_l >= prev_l else "down"

        for i in range(1, len(df)):
            cur_h, cur_l = highs[i], lows[i]
            prev_h, prev_l = out_high[-1], out_low[-1]
            contained = (
                (prev_l <= cur_l and prev_h >= cur_h)
                or (cur_l <= prev_l and cur_h >= prev_h)
            )
            if not contained:
                out_high.append(cur_h)
                out_low.append(cur_l)
                out_open.append(opens[i])
                out_close.append(closes[i])
                out_date.append(dates[i])
                out_vol.append(float(volumes[i]))
                out_raw_start.append(i)
                out_raw_end.append(i)
                out_high_raw.append(i)
                out_low_raw.append(i)
                out_inclusion_direction.append(None)
                continue

            before_h = out_high[-2] if len(out_high) >= 2 else prev_h
            before_l = out_low[-2] if len(out_low) >= 2 else prev_l
            direction = merge_direction(prev_h, prev_l, before_h, before_l, cur_h, cur_l)
            if direction == "up":
                if cur_h > prev_h:
                    out_high_raw[-1] = i
                if cur_l > prev_l:
                    out_low_raw[-1] = i
                out_high[-1] = max(prev_h, cur_h)
                out_low[-1] = max(prev_l, cur_l)
            else:
                if cur_h < prev_h:
                    out_high_raw[-1] = i
                if cur_l < prev_l:
                    out_low_raw[-1] = i
                out_high[-1] = min(prev_h, cur_h)
                out_low[-1] = min(prev_l, cur_l)
            out_close[-1] = closes[i]
            out_vol[-1] += float(volumes[i])
            out_raw_end[-1] = i
            out_inclusion_direction[-1] = direction
            # 保留既有代表日期语义，同时另存高低极值各自的精确原始日期。
            direction_raw_idx = out_high_raw[-1] if direction == "up" else out_low_raw[-1]
            out_date[-1] = dates[direction_raw_idx]

        self.klines = pd.DataFrame({
            "date": out_date,
            "open": out_open,
            "high": out_high,
            "low": out_low,
            "close": out_close,
            "volume": out_vol,
            "raw_start_idx": out_raw_start,
            "raw_end_idx": out_raw_end,
            "high_raw_idx": out_high_raw,
            "low_raw_idx": out_low_raw,
            "high_date": [dates[idx] for idx in out_high_raw],
            "low_date": [dates[idx] for idx in out_low_raw],
            "inclusion_direction": out_inclusion_direction,
        }).reset_index(drop=True)

    def detect(self) -> list[Fenxing]:
        """
        Detect strict three-bar fractals.

        Top: middle high and low are both higher than neighbours.
        Bottom: middle high and low are both lower than neighbours.
        """
        df = self.klines
        n = len(df)
        if n < 3:
            return []

        highs = df["high"].to_numpy(dtype=float)
        lows = df["low"].to_numpy(dtype=float)
        dates = df["date"].tolist()
        high_dates = df["high_date"].tolist() if "high_date" in df.columns else dates
        low_dates = df["low_date"].tolist() if "low_date" in df.columns else dates
        high_raw_indices = (
            df["high_raw_idx"].to_numpy(dtype=int)
            if "high_raw_idx" in df.columns
            else np.arange(n)
        )
        low_raw_indices = (
            df["low_raw_idx"].to_numpy(dtype=int)
            if "low_raw_idx" in df.columns
            else np.arange(n)
        )
        raw_starts = (
            df["raw_start_idx"].to_numpy(dtype=int)
            if "raw_start_idx" in df.columns
            else np.arange(n)
        )
        raw_ends = (
            df["raw_end_idx"].to_numpy(dtype=int)
            if "raw_end_idx" in df.columns
            else np.arange(n)
        )
        fenxings: list[Fenxing] = []

        prev_h = highs[:-2]
        prev_l = lows[:-2]
        mid_h = highs[1:-1]
        mid_l = lows[1:-1]
        next_h = highs[2:]
        next_l = lows[2:]

        top_mask = (
            (mid_h > prev_h)
            & (mid_h > next_h)
            & (mid_l > prev_l)
            & (mid_l > next_l)
        )
        bottom_mask = (
            (mid_h < prev_h)
            & (mid_h < next_h)
            & (mid_l < prev_l)
            & (mid_l < next_l)
        )

        for i in np.flatnonzero(top_mask):
            idx = int(i) + 1
            fenxings.append(
                Fenxing(
                    date=high_dates[idx],
                    type="top",
                    high=float(mid_h[i]),
                    low=float(mid_l[i]),
                    index=idx,
                    raw_index=int(high_raw_indices[idx]),
                    raw_start_idx=int(raw_starts[idx]),
                    raw_end_idx=int(raw_ends[idx]),
                )
            )

        for i in np.flatnonzero(bottom_mask):
            idx = int(i) + 1
            fenxings.append(
                Fenxing(
                    date=low_dates[idx],
                    type="bottom",
                    high=float(mid_h[i]),
                    low=float(mid_l[i]),
                    index=idx,
                    raw_index=int(low_raw_indices[idx]),
                    raw_start_idx=int(raw_starts[idx]),
                    raw_end_idx=int(raw_ends[idx]),
                )
            )

        fenxings.sort(key=lambda f: f.index)
        return fenxings
