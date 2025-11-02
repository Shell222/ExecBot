from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import pandas as pd
from bar import Bar


@dataclass
class Pivot:
    price: float
    is_low: bool
    idx: int
    prop: dict = None


class Zigzag:
    def __init__(self, pct_change=5):
        self.pct_change = pct_change
        self.pivots: List[Pivot] = []
        self.bar_info: List[dict] = []
        self.bars_cache: List[Bar] = []  # Cache bars for plot data preparation

    def update_info(self):
        if len(self.pivots) < 2:
            return

    def HandleBar(self, bar: Bar):
        # Store bar for plot data preparation
        self.bars_cache.append(bar)

        # Placeholder implementation for zigzag logic
        high = bar.high
        low = bar.low
        idx = bar.idx
        if len(self.pivots) == 0:
            p = Pivot(price=low, idx=idx, is_low=True)
            self.pivots.append(p)
            return
        last_pivot = self.pivots[-1]
        if last_pivot.is_low:
            if high >= last_pivot.price * (1 + self.pct_change / 100):
                #! Found Price in opposite direction
                p = Pivot(price=high, idx=idx, is_low=False)
                self.pivots.append(p)
                return
            if low <= last_pivot.price:
                #! Extend current edge
                last_pivot.price = low
                last_pivot.idx = idx
        else:
            if low <= last_pivot.price * (1 - self.pct_change / 100):
                #! Found Price in opposite direction
                p = Pivot(price=low, idx=idx, is_low=True)
                self.pivots.append(p)
                return
            if high >= last_pivot.price:
                #! Extend current edge
                last_pivot.price = high
                last_pivot.idx = idx

    def get_plot_data(self, bars: List[Bar]) -> pd.DataFrame:
        """
        Prepare pivot data for plotting.

        Args:
            bars: List of all bars for index mapping

        Returns:
            DataFrame with pivot plot data
        """
        if not self.pivots:
            return pd.DataFrame()

        pivot_data = {
            "datetime": [],
            "plot_index": [],
            "price": [],
            "is_low": [],
            "color": [],
        }

        for pivot in self.pivots:
            # Find the corresponding bar for this pivot
            matching_bar_idx = next(
                (i for i, bar in enumerate(bars) if bar.idx == pivot.idx), None
            )
            if matching_bar_idx is not None:
                matching_bar = bars[matching_bar_idx]
                pivot_data["datetime"].append(matching_bar.time)
                pivot_data["plot_index"].append(matching_bar_idx)
                pivot_data["price"].append(pivot.price)
                pivot_data["is_low"].append(pivot.is_low)
                pivot_data["color"].append("blue" if pivot.is_low else "orange")

        return pd.DataFrame(pivot_data)

    def update_plot_sources(self, plot_sources: Dict[str, Any], bars: List[Bar]):
        """
        Update Bokeh plot data sources with current zigzag data.

        Args:
            plot_sources: Dictionary containing Bokeh ColumnDataSource objects
            bars: List of all bars for index mapping
        """
        pivot_df = self.get_plot_data(bars)

        if "pivot_data_source" in plot_sources and plot_sources["pivot_data_source"]:
            if not pivot_df.empty:
                plot_sources["pivot_data_source"].data = pivot_df
            else:
                # Clear the data source if no pivots
                plot_sources["pivot_data_source"].data = {
                    "datetime": [],
                    "plot_index": [],
                    "price": [],
                    "is_low": [],
                    "color": [],
                }
