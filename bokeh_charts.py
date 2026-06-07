"""
Bokeh Charts for Stock Analysis

This module provides Bokeh chart implementations for displaying
stock data with candlestick charts and additional features.
"""

import pandas as pd
from datetime import datetime
from typing import List, Optional
import streamlit as st

from bokeh.plotting import figure
from bokeh.models import (
    ColumnDataSource,
    HoverTool,
    DatetimeTickFormatter,
    CrosshairTool,
    PanTool,
    BoxZoomTool,
    ResetTool,
    WheelZoomTool,
    CheckboxGroup,
    TextInput,
    CustomJS,
    PolyDrawTool,
    PolyEditTool,
)
from bokeh.layouts import column, row
from bokeh.io import curdoc
from bokeh.themes import Theme

from playground.bar import Bar

# Chart dimension constants
CHART_WIDTH = 1200
CHART_HEIGHT = 600


class BokehCandlestickChart:
    """Bokeh candlestick chart implementation with enhanced features"""

    # Wick width as a ratio of body width (e.g., 0.2 means wick is 20% of body width)
    WICK_TO_BODY_RATIO = 0.3

    def __init__(self, width: int = CHART_WIDTH, height: int = CHART_HEIGHT):
        self.width = width
        self.height = height
        self.chart = None
        self.data_source = None
        self.dot_data_source = None
        self.dot_renderer = None
        self.weekly_renderers = []
        self.weekly_dot_renderer = None
        self.effort_pace_renderer = None
        self.daily_renderers = []

    def create_chart(
        self,
        bars_data: pd.DataFrame,
        title: str = "Stock Price Chart",
        weekly_data: Optional[pd.DataFrame] = None,
        show_dots: bool = True,
        full_bars_data: Optional[pd.DataFrame] = None,
        weekly_bars_dict: Optional[dict] = None,
        bars: Optional[List[Bar]] = None,
        weekly_bars: Optional[List[Bar]] = None,
        normalized_bars_data: Optional[pd.DataFrame] = None,
        normalized_weekly_data: Optional[pd.DataFrame] = None,
        normalized_bars: Optional[List[Bar]] = None,
        normalized_weekly_bars: Optional[List[Bar]] = None,
    ):
        """Create an interactive Bokeh candlestick chart with controls"""

        if bars_data.empty:
            # Return empty chart if no data
            p = figure(width=self.width, height=self.height, title="No Data Available")
            return p

        # Use full data if provided, otherwise use bars_data
        if full_bars_data is None:
            full_bars_data = bars_data

        # Prepare data for candlestick chart
        chart_data = self._prepare_chart_data(full_bars_data, bars)

        # Create data source
        self.data_source = ColumnDataSource(chart_data)

        # Create separate data source for dots (always has full data)
        self.dot_data_source = ColumnDataSource(chart_data)

        # Create data source for polygon drawing (multi_line format)
        polygon_source = ColumnDataSource(data=dict(xs=[], ys=[]))

        # Create data source for midpoints
        midpoint_source = ColumnDataSource(data=dict(x=[], y=[]))

        # Create figure with tools
        wheel_zoom = WheelZoomTool()
        tools = [
            PanTool(),
            BoxZoomTool(),
            wheel_zoom,
            ResetTool(),
            CrosshairTool(),
        ]

        p = figure(
            width=self.width,
            height=self.height,
            title=title,
            x_axis_type="datetime",
            tools=tools,
            toolbar_location="above",
            active_scroll=wheel_zoom,
        )

        # Add polygon renderer for PolyDrawTool and PolyEditTool using multi_line
        polygon_renderer = p.multi_line(
            xs="xs",
            ys="ys",
            source=polygon_source,
            color="orange",
            line_width=3,
            line_dash="solid",
        )

        # Add midpoint renderer (circles at midpoints of lines)
        midpoint_renderer = p.circle(
            x="x",
            y="y",
            source=midpoint_source,
            size=8,
            color="blue",
            alpha=0.7,
        )

        # Add drawing and editing tools
        poly_draw = PolyDrawTool(
            renderers=[polygon_renderer],
            drag=True,
        )
        poly_edit = PolyEditTool(
            renderers=[polygon_renderer],
        )
        p.add_tools(poly_draw)
        p.add_tools(poly_edit)

        # Add JavaScript callback to update midpoints when polygon changes
        polygon_source.js_on_change(
            "data",
            CustomJS(
                args=dict(
                    polygon_source=polygon_source, midpoint_source=midpoint_source
                ),
                code="""
            const xs = polygon_source.data['xs'];
            const ys = polygon_source.data['ys'];
            const midpoint_xs = [];
            const midpoint_ys = [];
            
            // Calculate midpoints for each line segment in each polygon
            for (let i = 0; i < xs.length; i++) {
                const line_xs = xs[i];
                const line_ys = ys[i];
                
                // Calculate midpoint for each segment
                for (let j = 0; j < line_xs.length - 1; j++) {
                    const mid_x = (line_xs[j] + line_xs[j + 1]) / 2;
                    const mid_y = (line_ys[j] + line_ys[j + 1]) / 2;
                    midpoint_xs.push(mid_x);
                    midpoint_ys.push(mid_y);
                }
            }
            
            midpoint_source.data = {x: midpoint_xs, y: midpoint_ys};
        """,
            ),
        )

        # Add candlestick elements (always create, control visibility later)
        self._add_candlestick_glyphs(p, show_dots=True)

        # Add control bar horizontal lines if bars data is available
        if bars is not None:
            self._add_close_connection_lines(p, bars, full_bars_data)
            self._add_control_bar_lines(p, bars)
            self._add_rejection_markers(p, bars)
            self._add_effort_pace_zones(p, bars)

        # Add weekly candlesticks if provided
        if weekly_data is not None and not weekly_data.empty:
            self._add_weekly_candlesticks(p, weekly_data, weekly_bars_dict, weekly_bars)
            # Show weekly candles by default
            for renderer in self.weekly_renderers:
                renderer.visible = True

        # Format axes
        self._format_axes(p)

        # Apply styling
        self._apply_styling(p)

        # Create interactive controls
        controls = self._create_controls(len(full_bars_data), show_dots)

        # Create pair trading chart if normalized data is provided
        if normalized_bars_data is not None and not normalized_bars_data.empty:
            p_pair = self._create_pair_trading_chart(
                normalized_bars_data,
                normalized_weekly_data,
                p,  # Link x-axis to main chart
                normalized_bars,
                normalized_weekly_bars,
            )
            layout = column(controls, p, p_pair)
        else:
            layout = column(controls, p)

        self.chart = p
        return layout

    def _prepare_chart_data(
        self, bars_data: pd.DataFrame, bars: Optional[List[Bar]] = None
    ) -> dict:
        """Prepare data for Bokeh candlestick chart"""

        # Calculate candlestick components
        bars_data = bars_data.copy()
        bars_data["body_top"] = bars_data[["open", "close"]].max(axis=1)
        bars_data["body_bottom"] = bars_data[["open", "close"]].min(axis=1)
        bars_data["body_height"] = bars_data["body_top"] - bars_data["body_bottom"]
        bars_data["body_middle"] = (
            bars_data["body_top"] + bars_data["body_bottom"]
        ) / 2

        # Calculate wick components
        bars_data["upper_wick_middle"] = (bars_data["high"] + bars_data["body_top"]) / 2
        bars_data["upper_wick_height"] = bars_data["high"] - bars_data["body_top"]
        bars_data["lower_wick_middle"] = (
            bars_data["low"] + bars_data["body_bottom"]
        ) / 2
        bars_data["lower_wick_height"] = bars_data["body_bottom"] - bars_data["low"]

        # Determine colors
        bars_data["color"] = bars_data.apply(
            lambda x: "green" if x["close"] >= x["open"] else "red", axis=1
        )

        # Dim colors for bars that close within previous bar's range
        # Calculate if close is within prev bar's range (prev_low <= close <= prev_high)
        bars_data["prev_high"] = bars_data["high"].shift(1)
        bars_data["prev_low"] = bars_data["low"].shift(1)
        bars_data["closes_within_prev"] = (
            bars_data["close"] >= bars_data["prev_low"]
        ) & (bars_data["close"] <= bars_data["prev_high"])

        # Apply dimming for bars that close within previous bar
        bars_data.loc[bars_data["closes_within_prev"], "color"] = bars_data.loc[
            bars_data["closes_within_prev"], "color"
        ].apply(lambda c: "lightgreen" if c == "green" else "lightcoral")

        # Use LastWeekBreakIndicator to determine border styling
        border_color = []
        border_width = []

        if bars is not None:
            for idx, bar in enumerate(bars):
                # Check if this bar is marked as first weekly breakout by LastWeekBreakIndicator
                last_week_break = bar.prop.get("last_week_break") if bar.prop else None

                if last_week_break in ["upside", "downside"]:
                    # First bar to break outside last week's range - black border
                    border_color.append("black")
                    border_width.append(2)
                else:
                    # Normal bars - use inc/dec color
                    border_color.append(bars_data.iloc[idx]["color"])
                    border_width.append(1)
        else:
            # No bars provided, use default border styling
            border_color = bars_data["color"].tolist()
            border_width = [1] * len(bars_data)

        bars_data["border_color"] = border_color
        bars_data["border_width"] = border_width

        # Calculate price change
        bars_data["price_change"] = bars_data["close"] - bars_data["open"]
        bars_data["price_change_pct"] = (
            bars_data["price_change"] / bars_data["open"] * 100
        ).round(2)

        # Extract indicator fields for tooltips
        if bars is not None:
            # Initialize tooltip fields
            movement_type = []
            movement_score = []
            alter_movement_score = []
            outer_movement_score = []
            bar_movement = []
            bar_pressure = []
            sma_range_20 = []
            control_bar_status = []
            control_bar_range = []
            rejection_type = []
            last_week_break = []
            last_week_high = []
            last_week_low = []
            effort_pace_direction = []
            effort_pace_range = []
            patterns = []
            my_trend = []

            for bar in bars:
                if bar.prop:
                    movement_type.append(bar.prop.get("movement_type", "-"))
                    movement_score.append(bar.prop.get("movement_score", 0))
                    alter_movement_score.append(bar.prop.get("alter_movement_score", 0))
                    outer_movement_score.append(bar.prop.get("outer_movement_score", 0))
                    bar_movement.append(bar.prop.get("bar_movement", 0))
                    bar_pressure.append(bar.prop.get("bar_pressure", 0))
                    sma_range_20.append(bar.prop.get("sma_range_20", 0))

                    # Control bar
                    control_bar = bar.prop.get("ControlBar")
                    if control_bar is not None:
                        control_bar_status.append("Controlled")
                        control_bar_range.append(
                            f"${control_bar.low:.2f} - ${control_bar.high:.2f}"
                        )
                    else:
                        control_bar_status.append("New Control Bar")
                        control_bar_range.append("-")

                    # Rejection
                    rejection = bar.prop.get("ImmediateRejection")
                    rejection_type.append(rejection.upper() if rejection else "-")

                    # Last week break
                    lwb = bar.prop.get("last_week_break")
                    last_week_break.append(lwb.upper() if lwb else "-")
                    last_week_high.append(bar.prop.get("last_week_high", 0))
                    last_week_low.append(bar.prop.get("last_week_low", 0))

                    # Effort Pace
                    ep = bar.prop.get("EffortPace")
                    if ep:
                        effort_pace_direction.append(
                            "Bullish" if ep["is_bullish"] else "Bearish"
                        )
                        effort_pace_range.append(
                            f"${ep['bottom']:.2f} - ${ep['top']:.2f}"
                        )
                    else:
                        effort_pace_direction.append("-")
                        effort_pace_range.append("-")

                    # Patterns
                    detected = bar.prop.get("detected_patterns", [])
                    patterns.append(", ".join(detected) if detected else "-")

                    # MyTrend
                    my_trend.append(bar.prop.get("MyTrend", "-"))
                else:
                    # No properties
                    movement_type.append("-")
                    movement_score.append(0)
                    alter_movement_score.append(0)
                    outer_movement_score.append(0)
                    bar_movement.append(0)
                    bar_pressure.append(0)
                    sma_range_20.append(0)
                    control_bar_status.append("-")
                    control_bar_range.append("-")
                    rejection_type.append("-")
                    last_week_break.append("-")
                    last_week_high.append(0)
                    last_week_low.append(0)
                    effort_pace_direction.append("-")
                    effort_pace_range.append("-")
                    patterns.append("-")
                    my_trend.append("-")

            bars_data["movement_type"] = movement_type
            bars_data["movement_score"] = movement_score
            bars_data["alter_movement_score"] = alter_movement_score
            bars_data["outer_movement_score"] = outer_movement_score
            bars_data["bar_movement"] = bar_movement
            bars_data["bar_pressure"] = bar_pressure
            bars_data["sma_range_20"] = sma_range_20
            bars_data["control_bar_status"] = control_bar_status
            bars_data["control_bar_range"] = control_bar_range
            bars_data["rejection_type"] = rejection_type
            bars_data["last_week_break"] = last_week_break
            bars_data["last_week_high"] = last_week_high
            bars_data["last_week_low"] = last_week_low
            bars_data["effort_pace_direction"] = effort_pace_direction
            bars_data["effort_pace_range"] = effort_pace_range
            bars_data["patterns"] = patterns
            bars_data["my_trend"] = my_trend
        else:
            # Set default values for all tooltip fields
            bars_data["movement_type"] = "-"
            bars_data["movement_score"] = 0
            bars_data["alter_movement_score"] = 0
            bars_data["outer_movement_score"] = 0
            bars_data["bar_movement"] = 0
            bars_data["bar_pressure"] = 0
            bars_data["sma_range_20"] = 0
            bars_data["control_bar_status"] = "-"
            bars_data["control_bar_range"] = "-"
            bars_data["rejection_type"] = "-"
            bars_data["last_week_break"] = "-"
            bars_data["last_week_high"] = 0
            bars_data["last_week_low"] = 0
            bars_data["effort_pace_direction"] = "-"
            bars_data["effort_pace_range"] = "-"
            bars_data["patterns"] = "-"
            bars_data["my_trend"] = "-"

        return {
            "datetime": bars_data["datetime"],
            "open": bars_data["open"],
            "high": bars_data["high"],
            "low": bars_data["low"],
            "close": bars_data["close"],
            "volume": bars_data["volume"],
            "body_top": bars_data["body_top"],
            "body_bottom": bars_data["body_bottom"],
            "body_middle": bars_data["body_middle"],
            "body_height": bars_data["body_height"],
            "upper_wick_middle": bars_data["upper_wick_middle"],
            "upper_wick_height": bars_data["upper_wick_height"],
            "lower_wick_middle": bars_data["lower_wick_middle"],
            "lower_wick_height": bars_data["lower_wick_height"],
            "color": bars_data["color"],
            "border_color": bars_data["border_color"],
            "border_width": bars_data["border_width"],
            "price_change": bars_data["price_change"],
            "price_change_pct": bars_data["price_change_pct"],
            "movement_type": bars_data["movement_type"],
            "movement_score": bars_data["movement_score"],
            "alter_movement_score": bars_data["alter_movement_score"],
            "outer_movement_score": bars_data["outer_movement_score"],
            "bar_movement": bars_data["bar_movement"],
            "bar_pressure": bars_data["bar_pressure"],
            "sma_range_20": bars_data["sma_range_20"],
            "control_bar_status": bars_data["control_bar_status"],
            "control_bar_range": bars_data["control_bar_range"],
            "rejection_type": bars_data["rejection_type"],
            "last_week_break": bars_data["last_week_break"],
            "last_week_high": bars_data["last_week_high"],
            "last_week_low": bars_data["last_week_low"],
            "effort_pace_direction": bars_data["effort_pace_direction"],
            "effort_pace_range": bars_data["effort_pace_range"],
            "patterns": bars_data["patterns"],
            "my_trend": bars_data["my_trend"],
        }

    def _add_candlestick_glyphs(self, p: figure, show_dots: bool = True) -> None:
        """Add candlestick visual elements to the chart"""

        # Body width and wick width in milliseconds
        body_width_ms = 1000 * 60 * 60 * 12  # 12 hours in milliseconds as default width
        wick_width_ms = body_width_ms * self.WICK_TO_BODY_RATIO

        # Upper wicks (body_top to high) as rectangles
        r1 = p.rect(
            x="datetime",
            y="upper_wick_middle",
            width=wick_width_ms,
            height="upper_wick_height",
            source=self.data_source,
            fill_color="color",
            line_color="color",
            line_width=0,
        )
        self.daily_renderers.append(r1)

        # Lower wicks (low to body_bottom) as rectangles
        r2 = p.rect(
            x="datetime",
            y="lower_wick_middle",
            width=wick_width_ms,
            height="lower_wick_height",
            source=self.data_source,
            fill_color="color",
            line_color="color",
            line_width=0,
        )
        self.daily_renderers.append(r2)

        # Bodies (open-close rectangles)
        # Calculate dynamic width based on data points
        width_ms = body_width_ms  # Use the same body_width_ms variable

        r3 = p.rect(
            x="datetime",
            y="body_middle",
            width=width_ms,
            height="body_height",
            source=self.data_source,
            fill_color="color",
            line_color="border_color",
            line_width="border_width",
            fill_alpha=0.8,
        )
        self.daily_renderers.append(r3)

        # Add hover tool for detailed bar analysis
        hover = HoverTool(
            renderers=[r3],
            tooltips=[
                ("Time", "@datetime{%F %H:%M}"),
                ("", ""),
                ("Open", "@open{$0.00}"),
                ("High", "@high{$0.00}"),
                ("Low", "@low{$0.00}"),
                ("Close", "@close{$0.00}"),
                ("Volume", "@volume{0,0}"),
                ("Range", "@price_change{+$0.00}"),
                ("Change %", "@price_change_pct{+0.00}%"),
                ("", ""),
                ("Movement Type", "@movement_type"),
                ("Movement Score", "@movement_score{0.00}"),
                ("Alt Score", "@alter_movement_score{0.00}"),
                ("Outer Score", "@outer_movement_score{0.00}"),
                ("", ""),
                ("Bar Movement", "@bar_movement{$0.00}"),
                ("Bar Pressure", "@bar_pressure{$0.00}"),
                ("SMA Range (20)", "@sma_range_20{$0.00}"),
                ("", ""),
                ("Control Bar", "@control_bar_status"),
                ("Control Range", "@control_bar_range"),
                ("Rejection", "@rejection_type"),
                ("", ""),
                ("Weekly Break", "@last_week_break"),
                ("Last Week High", "@last_week_high{$0.00}"),
                ("Last Week Low", "@last_week_low{$0.00}"),
                ("", ""),
                ("Effort Pace", "@effort_pace_direction"),
                ("EP Range", "@effort_pace_range"),
                ("", ""),
                ("My Trend", "@my_trend"),
                ("Patterns", "@patterns"),
            ],
            formatters={"@datetime": "datetime"},
        )
        p.add_tools(hover)

        # Add black dots at close prices (using separate data source)
        self.dot_renderer = p.circle(
            x="datetime",
            y="close",
            size=5,
            source=self.dot_data_source,
            fill_color="black",
            line_color="black",
        )
        self.dot_renderer.visible = show_dots

    def _add_close_connection_lines(
        self, p: figure, bars: List[Bar], bars_data: pd.DataFrame
    ) -> None:
        """Add blue lines connecting close prices when bar closes within previous bar's range"""
        line_data = {"x0": [], "y0": [], "x1": [], "y1": []}

        for i in range(1, len(bars)):
            # Check if current bar closes within previous bar's range
            prev_bar = bars[i - 1]
            curr_bar = bars[i]

            if prev_bar.low <= curr_bar.close <= prev_bar.high:
                # Add line from prev close to current close
                line_data["x0"].append(prev_bar.time)
                line_data["y0"].append(prev_bar.close)
                line_data["x1"].append(curr_bar.time)
                line_data["y1"].append(curr_bar.close)

        # Draw all connection lines in one batch
        if line_data["x0"]:
            connection_source = ColumnDataSource(data=line_data)
            p.segment(
                x0="x0",
                y0="y0",
                x1="x1",
                y1="y1",
                source=connection_source,
                line_color="blue",
                line_width=2,
                line_alpha=1,
            )

    def _add_control_bar_lines(self, p: figure, bars: List[Bar]) -> None:
        """Add horizontal dotted lines from control bars to their last controlled bar"""
        # Build a map of control bar to list of controlled bar indices
        control_bar_ranges = {}  # control_bar_idx -> (start_idx, end_idx)

        for i, bar in enumerate(bars):
            if bar.prop and bar.prop.get("ControlBar") is not None:
                control_bar = bar.prop["ControlBar"]
                # Find the control bar index
                try:
                    control_bar_idx = bars.index(control_bar)
                    if control_bar_idx not in control_bar_ranges:
                        control_bar_ranges[control_bar_idx] = [i, i]
                    else:
                        control_bar_ranges[control_bar_idx][1] = i  # Update end index
                except ValueError:
                    continue  # Control bar not in list

        # Collect all line data for batched rendering
        line_data = {
            "x0": [],
            "y0": [],
            "x1": [],
            "y1": [],
        }

        for control_bar_idx, (start_idx, end_idx) in control_bar_ranges.items():
            control_bar = bars[control_bar_idx]
            last_controlled_bar = bars[end_idx]

            # Add high line
            line_data["x0"].append(control_bar.time)
            line_data["y0"].append(control_bar.high)
            line_data["x1"].append(last_controlled_bar.time)
            line_data["y1"].append(control_bar.high)

            # Add low line
            line_data["x0"].append(control_bar.time)
            line_data["y0"].append(control_bar.low)
            line_data["x1"].append(last_controlled_bar.time)
            line_data["y1"].append(control_bar.low)

        # Create single ColumnDataSource for all control bar lines
        if line_data["x0"]:
            control_lines_source = ColumnDataSource(data=line_data)
            p.segment(
                x0="x0",
                y0="y0",
                x1="x1",
                y1="y1",
                source=control_lines_source,
                line_color="gray",
                line_width=2,
                line_dash="dotted",
                line_alpha=1.0,
            )

    def _add_rejection_markers(self, p: figure, bars: List[Bar]) -> None:
        """Add emoji markers for bars with immediate rejection"""
        upside_rejection_data = {"x": [], "y": [], "text": []}
        downside_rejection_data = {"x": [], "y": [], "text": []}

        for bar in bars:
            if bar.prop and bar.prop.get("ImmediateRejection"):
                rejection_type = bar.prop["ImmediateRejection"]

                if rejection_type in ["upside", "both"]:
                    # Upside rejection: bar went above control bar but rejected down
                    # Show marker above the bar (bearish)
                    upside_rejection_data["x"].append(bar.time)
                    upside_rejection_data["y"].append(bar.high)
                    upside_rejection_data["text"].append("🔻")

                if rejection_type in ["downside", "both"]:
                    # Downside rejection: bar went below control bar but rejected up
                    # Show marker below the bar (bullish)
                    downside_rejection_data["x"].append(bar.time)
                    downside_rejection_data["y"].append(bar.low)
                    downside_rejection_data["text"].append("🔺")

        # Add upside rejection markers (above bars - bearish)
        if upside_rejection_data["x"]:
            upside_source = ColumnDataSource(data=upside_rejection_data)
            p.text(
                x="x",
                y="y",
                text="text",
                source=upside_source,
                text_font_size="16pt",
                text_align="center",
                text_baseline="bottom",
                y_offset=5,
            )

        # Add downside rejection markers (below bars - bullish)
        if downside_rejection_data["x"]:
            downside_source = ColumnDataSource(data=downside_rejection_data)
            p.text(
                x="x",
                y="y",
                text="text",
                source=downside_source,
                text_font_size="16pt",
                text_align="center",
                text_baseline="top",
                y_offset=-5,
            )

    def _add_effort_pace_zones(self, p: figure, bars: List[Bar]) -> None:
        """Add rectangles for EffortPace zones (body overlap with prev bar's range)"""
        effort_pace_data = {"x": [], "y": [], "width": [], "height": [], "color": []}

        # Body width in milliseconds (same as candlestick body)
        body_width_ms = 1000 * 60 * 60 * 12  # 12 hours

        for bar in bars:
            if bar.prop and bar.prop.get("EffortPace"):
                effort_pace = bar.prop["EffortPace"]
                bottom = effort_pace["bottom"]
                top = effort_pace["top"]
                is_bullish = effort_pace["is_bullish"]

                # Calculate rectangle properties
                height = top - bottom
                middle = (top + bottom) / 2

                effort_pace_data["x"].append(bar.time)
                effort_pace_data["y"].append(middle)
                effort_pace_data["width"].append(body_width_ms)
                effort_pace_data["height"].append(height)
                effort_pace_data["color"].append("blue" if is_bullish else "purple")

        # Add EffortPace zone rectangles
        if effort_pace_data["x"]:
            effort_pace_source = ColumnDataSource(data=effort_pace_data)
            self.effort_pace_renderer = p.rect(
                x="x",
                y="y",
                width="width",
                height="height",
                source=effort_pace_source,
                fill_color="color",
                line_color="color",
                fill_alpha=0.3,
                line_width=1,
            )

    def _add_weekly_rejection_markers(self, p: figure, weekly_bars: List[Bar]) -> None:
        """Add emoji markers for weekly bars with immediate rejection (different emoji)"""
        upside_rejection_data = {"x": [], "y": [], "text": []}
        downside_rejection_data = {"x": [], "y": [], "text": []}

        for bar in weekly_bars:
            if bar.prop and bar.prop.get("ImmediateRejection"):
                rejection_type = bar.prop["ImmediateRejection"]

                if rejection_type in ["upside", "both"]:
                    # Weekly upside rejection: use ⬇️ (downward arrow)
                    upside_rejection_data["x"].append(bar.time)
                    upside_rejection_data["y"].append(bar.high)
                    upside_rejection_data["text"].append("⬇️")

                if rejection_type in ["downside", "both"]:
                    # Weekly downside rejection: use ⬆️ (upward arrow)
                    downside_rejection_data["x"].append(bar.time)
                    downside_rejection_data["y"].append(bar.low)
                    downside_rejection_data["text"].append("⬆️")

        # Add weekly upside rejection markers (above bars)
        if upside_rejection_data["x"]:
            upside_source = ColumnDataSource(data=upside_rejection_data)
            upside_renderer = p.text(
                x="x",
                y="y",
                text="text",
                source=upside_source,
                text_font_size="20pt",
                text_align="center",
                text_baseline="bottom",
                y_offset=8,
            )
            self.weekly_renderers.append(upside_renderer)

        # Add weekly downside rejection markers (below bars)
        if downside_rejection_data["x"]:
            downside_source = ColumnDataSource(data=downside_rejection_data)
            downside_renderer = p.text(
                x="x",
                y="y",
                text="text",
                source=downside_source,
                text_font_size="20pt",
                text_align="center",
                text_baseline="top",
                y_offset=-8,
            )
            self.weekly_renderers.append(downside_renderer)

    def _add_weekly_candlesticks(
        self,
        p: figure,
        weekly_data: pd.DataFrame,
        weekly_bars_dict: Optional[dict] = None,
        weekly_bars: Optional[List[Bar]] = None,
    ) -> None:
        """Add weekly aggregated candlesticks with WeekProfile (body casting method)"""
        from datetime import timedelta

        # Prepare weekly chart data with hover text
        weekly_chart_data = self._prepare_chart_data(weekly_data, weekly_bars)

        # Add bar colors based on control bar status
        if weekly_bars:
            bar_colors = []
            for bar in weekly_bars:
                if bar.prop:
                    control_bar = bar.prop.get("ControlBar")
                    if control_bar is None:
                        # Not controlled: color based on open/close
                        if bar.close >= bar.open:
                            color = "green"  # Bullish
                        else:
                            color = "red"  # Bearish
                    else:
                        # Controlled: check if it breaks out
                        if bar.close > control_bar.high:
                            color = "lime"  # Bright green for upward break
                        elif bar.close < control_bar.low:
                            color = "orangered"  # Red for downward break
                        else:
                            color = "gray"  # Controlled, no break
                else:
                    # No properties: default based on open/close
                    color = "green" if bar.close >= bar.open else "red"
                bar_colors.append(color)
            weekly_chart_data["bar_color"] = bar_colors

        # Calculate box coordinates for weekly bars (Sunday to Saturday)
        box_data = {"x": [], "y": [], "width": [], "height": [], "color": []}

        for i, weekly_dt in enumerate(weekly_chart_data["datetime"]):
            # weekly_dt is Saturday noon
            # Calculate Sunday of previous week (7 days before Saturday)
            sunday_prev_week = weekly_dt - timedelta(days=6)  # Go back to Sunday
            saturday_current_week = weekly_dt + timedelta(
                hours=12
            )  # Saturday end of day

            # Box spans from Sunday to Saturday
            # Calculate midpoint: sunday + half the time difference
            time_diff = saturday_current_week - sunday_prev_week
            box_center_x = sunday_prev_week + time_diff / 2
            box_width_ms = time_diff.total_seconds() * 1000

            # Box spans from weekly low to weekly high
            low = weekly_chart_data["low"][i]
            high = weekly_chart_data["high"][i]
            box_center_y = (low + high) / 2
            box_height = high - low

            box_data["x"].append(box_center_x)
            box_data["y"].append(box_center_y)
            box_data["width"].append(box_width_ms)
            box_data["height"].append(box_height)
            box_data["color"].append(
                weekly_chart_data["bar_color"][i]
                if "bar_color" in weekly_chart_data
                else "black"
            )

        # Draw weekly boxes
        if box_data["x"]:
            box_source = ColumnDataSource(data=box_data)
            box_renderer = p.rect(
                x="x",
                y="y",
                width="width",
                height="height",
                source=box_source,
                fill_color=None,
                line_color="color",
                line_width=2,
                line_alpha=0.8,
            )
            self.weekly_renderers.append(box_renderer)

        weekly_source = ColumnDataSource(weekly_chart_data)

        # Add dot at close price
        self.weekly_dot_renderer = p.circle(
            x="datetime",
            y="close",
            size=5,
            source=weekly_source,
            fill_color="black",
            line_color="black",
            line_width=1,
        )

        # Add hover tool for weekly bars on close dots
        weekly_hover = HoverTool(
            renderers=[self.weekly_dot_renderer],
            tooltips=[
                ("Week Ending", "@datetime{%F}"),
                ("", ""),
                ("Open", "@open{$0.00}"),
                ("High", "@high{$0.00}"),
                ("Low", "@low{$0.00}"),
                ("Close", "@close{$0.00}"),
                ("Volume", "@volume{0,0}"),
                ("Range", "@price_change{+$0.00}"),
                ("Change %", "@price_change_pct{+0.00}%"),
                ("", ""),
                ("Movement Type", "@movement_type"),
                ("Movement Score", "@movement_score{0.00}"),
                ("Alt Score", "@alter_movement_score{0.00}"),
                ("Outer Score", "@outer_movement_score{0.00}"),
                ("", ""),
                ("Bar Movement", "@bar_movement{$0.00}"),
                ("Bar Pressure", "@bar_pressure{$0.00}"),
                ("SMA Range (20)", "@sma_range_20{$0.00}"),
                ("", ""),
                ("Control Bar", "@control_bar_status"),
                ("Control Range", "@control_bar_range"),
                ("Rejection", "@rejection_type"),
                ("", ""),
                ("Weekly Break", "@last_week_break"),
                ("Last Week High", "@last_week_high{$0.00}"),
                ("Last Week Low", "@last_week_low{$0.00}"),
                ("", ""),
                ("Effort Pace", "@effort_pace_direction"),
                ("EP Range", "@effort_pace_range"),
                ("", ""),
                ("My Trend", "@my_trend"),
                ("Patterns", "@patterns"),
            ],
            formatters={"@datetime": "datetime"},
        )
        p.add_tools(weekly_hover)

        # Add weekly rejection markers (different emoji than daily)
        if weekly_bars:
            self._add_weekly_rejection_markers(p, weekly_bars)

    def _create_controls(self, max_candles: int, show_dots_default: bool):
        """Create interactive controls with JavaScript callbacks"""

        # Store original data for slider filtering
        original_data = dict(self.data_source.data)

        # Checkbox for display options
        checkbox = CheckboxGroup(
            labels=[
                "Show Weekly Candles",
                "Show Close Dots",
                "Show Weekly Dots",
                "Show EffortPace Zones",
            ],
            active=([0, 1, 2, 3] if show_dots_default else [0]),
        )

        # Text input for number of candles
        text_input = TextInput(
            value=str(min(50, max_candles)),
            title="Candles to Display:",
            width=150,
        )

        # JavaScript callback for checkbox
        checkbox_callback = CustomJS(
            args=dict(
                dot_renderer=self.dot_renderer,
                weekly_renderers=self.weekly_renderers,
                weekly_dot_renderer=self.weekly_dot_renderer,
                effort_pace_renderer=(
                    self.effort_pace_renderer
                    if hasattr(self, "effort_pace_renderer")
                    else None
                ),
            ),
            code="""
                // 0 = Show Weekly Candles, 1 = Show Close Dots, 2 = Show Weekly Dots,
                // 3 = Show EffortPace Zones
                const show_weekly = checkbox.active.includes(0);
                const show_dots = checkbox.active.includes(1);
                const show_weekly_dots = checkbox.active.includes(2);
                const show_effort_pace = checkbox.active.includes(3);
                
                // Toggle daily dot visibility
                dot_renderer.visible = show_dots;
                
                // Toggle weekly candles visibility
                for (let i = 0; i < weekly_renderers.length; i++) {
                    weekly_renderers[i].visible = show_weekly;
                }
                
                // Toggle weekly dot visibility
                if (weekly_dot_renderer) {
                    weekly_dot_renderer.visible = show_weekly_dots;
                }
                
                // Toggle EffortPace zones visibility
                if (effort_pace_renderer) {
                    effort_pace_renderer.visible = show_effort_pace;
                }
            """,
        )
        checkbox_callback.args["checkbox"] = checkbox
        checkbox.js_on_change("active", checkbox_callback)

        # JavaScript callback for text input
        input_callback = CustomJS(
            args=dict(
                source=self.data_source,
                original_data=original_data,
                max_candles=max_candles,
            ),
            code="""
                let num_candles = parseInt(text_input.value);
                const total_candles = original_data['datetime'].length;
                
                // Validate input
                if (isNaN(num_candles) || num_candles < 1) {
                    num_candles = 10;
                    text_input.value = "10";
                }
                if (num_candles > max_candles) {
                    num_candles = max_candles;
                    text_input.value = String(max_candles);
                }
                
                const start_idx = Math.max(0, total_candles - num_candles);
                
                // Update data source with slice from original data
                const new_data = {};
                for (const key in original_data) {
                    new_data[key] = original_data[key].slice(start_idx);
                }
                source.data = new_data;
                source.change.emit();
            """,
        )
        input_callback.args["text_input"] = text_input
        text_input.js_on_change("value", input_callback)

        return row(checkbox, text_input)

    def _add_hover_tool(self, p: figure) -> None:
        """Add interactive hover tooltip"""

        hover = HoverTool(
            tooltips=[
                ("Date", "@datetime{%F}"),
                ("Open", "@open{$0.00}"),
                ("High", "@high{$0.00}"),
                ("Low", "@low{$0.00}"),
                ("Close", "@close{$0.00}"),
                ("Change", "@price_change{+$0.00}"),
                ("Change %", "@price_change_pct{+0.00}%"),
                ("Volume", "@volume{0,0}"),
            ],
            formatters={"@datetime": "datetime"},
            mode="vline",
        )

        p.add_tools(hover)

    def _format_axes(self, p: figure) -> None:
        """Format chart axes"""

        # Format x-axis (datetime)
        p.xaxis.formatter = DatetimeTickFormatter(
            days="%m/%d", months="%m/%Y", years="%Y"
        )

        # Format y-axis (price)
        p.yaxis.axis_label = "Price ($)"
        p.xaxis.axis_label = "Date"

        # Rotate x-axis labels for better readability
        p.xaxis.major_label_orientation = 0.8

    def _apply_styling(self, p: figure) -> None:
        """Apply visual styling to the chart"""

        # Grid styling
        p.grid.grid_line_alpha = 0.3
        p.grid.grid_line_dash = [6, 4]

        # Background
        p.background_fill_color = "#fafafa"
        p.border_fill_color = "white"

        # Title styling
        p.title.text_font_size = "14pt"
        p.title.align = "center"

        # Axis styling
        p.axis.axis_label_text_font_style = "bold"

    def update_data(self, new_bars_data: pd.DataFrame) -> None:
        """Update chart with new data"""
        if self.data_source is not None:
            chart_data = self._prepare_chart_data(new_bars_data)
            self.data_source.data = chart_data

    def _create_pair_trading_chart(
        self,
        normalized_bars_data: pd.DataFrame,
        normalized_weekly_data: Optional[pd.DataFrame],
        main_chart: figure,
        normalized_bars: Optional[List[Bar]] = None,
        normalized_weekly_bars: Optional[List[Bar]] = None,
    ) -> figure:
        """Create a pair trading chart (Stock/SPY * 100) with linked x-axis and all indicators"""

        # Prepare normalized chart data
        normalized_chart_data = self._prepare_chart_data(
            normalized_bars_data, normalized_bars
        )

        # Create data source for normalized data
        normalized_source = ColumnDataSource(normalized_chart_data)

        # Create figure with linked x-axis to main chart
        p_pair = figure(
            width=self.width,
            height=400,  # Smaller height for pair chart
            title="Pair Trading Chart (Stock/SPY × 100)",
            x_axis_type="datetime",
            x_range=main_chart.x_range,  # Link x-axis to main chart
            tools=[
                PanTool(),
                BoxZoomTool(),
                WheelZoomTool(),
                ResetTool(),
                CrosshairTool(),
            ],
            toolbar_location="above",
        )

        # Body width and wick width in milliseconds
        body_width_ms = 1000 * 60 * 60 * 12  # 12 hours
        wick_width_ms = body_width_ms * self.WICK_TO_BODY_RATIO

        # Add candlestick elements for normalized data
        # Upper wicks
        p_pair.rect(
            x="datetime",
            y="upper_wick_middle",
            width=wick_width_ms,
            height="upper_wick_height",
            source=normalized_source,
            fill_color="color",
            line_color="color",
            line_width=0,
        )

        # Lower wicks
        p_pair.rect(
            x="datetime",
            y="lower_wick_middle",
            width=wick_width_ms,
            height="lower_wick_height",
            source=normalized_source,
            fill_color="color",
            line_color="color",
            line_width=0,
        )

        # Bodies
        p_pair.rect(
            x="datetime",
            y="body_middle",
            width=body_width_ms,
            height="body_height",
            source=normalized_source,
            fill_color="color",
            line_color="color",
            line_width=1,
            fill_alpha=0.8,
        )

        # Add control bar lines if normalized bars are provided
        if normalized_bars is not None:
            self._add_close_connection_lines(
                p_pair, normalized_bars, normalized_bars_data
            )
            self._add_control_bar_lines(p_pair, normalized_bars)
            self._add_rejection_markers(p_pair, normalized_bars)
            self._add_effort_pace_zones(p_pair, normalized_bars)

        # Add normalized weekly bars if provided
        if normalized_weekly_data is not None and not normalized_weekly_data.empty:
            self._add_weekly_candlesticks(
                p_pair,
                normalized_weekly_data,
                None,  # weekly_bars_dict not needed for pair chart
                normalized_weekly_bars,
            )

        # Format axes
        p_pair.xaxis.formatter = DatetimeTickFormatter(
            days="%m/%d", months="%m/%Y", years="%Y"
        )
        p_pair.yaxis.axis_label = "Relative Strength"
        p_pair.xaxis.axis_label = "Date"
        p_pair.xaxis.major_label_orientation = 0.8

        # Apply styling
        p_pair.grid.grid_line_alpha = 0.3
        p_pair.grid.grid_line_dash = [6, 4]
        p_pair.background_fill_color = "#fafafa"
        p_pair.border_fill_color = "white"
        p_pair.title.text_font_size = "14pt"
        p_pair.title.align = "center"
        p_pair.axis.axis_label_text_font_style = "bold"

        return p_pair


def create_bokeh_candlestick_chart(
    bars_data: pd.DataFrame,
    title: str = "Stock Price Chart",
    weekly_data: Optional[pd.DataFrame] = None,
    show_dots: bool = True,
    full_bars_data: Optional[pd.DataFrame] = None,
    weekly_bars_dict: Optional[dict] = None,
    bars: Optional[List[Bar]] = None,
    weekly_bars: Optional[List[Bar]] = None,
    normalized_bars_data: Optional[pd.DataFrame] = None,
    normalized_weekly_data: Optional[pd.DataFrame] = None,
    normalized_bars: Optional[List[Bar]] = None,
    normalized_weekly_bars: Optional[List[Bar]] = None,
):
    """Create a Bokeh candlestick chart for Streamlit display"""

    chart = BokehCandlestickChart(width=CHART_WIDTH, height=CHART_HEIGHT)
    bokeh_layout = chart.create_chart(
        bars_data,
        title,
        weekly_data,
        show_dots,
        full_bars_data,
        weekly_bars_dict,
        bars,
        weekly_bars,
        normalized_bars_data,
        normalized_weekly_data,
        normalized_bars,
        normalized_weekly_bars,
    )

    return bokeh_layout


def bars_to_dataframe(bars: List[Bar]):
    """Convert Bar objects to DataFrame for charting

    Returns:
        Tuple of (DataFrame, bars list) for charting with control bar support
    """

    if not bars:
        return pd.DataFrame(), []

    data = {
        "datetime": [bar.time for bar in bars],
        "open": [bar.open for bar in bars],
        "high": [bar.high for bar in bars],
        "low": [bar.low for bar in bars],
        "close": [bar.close for bar in bars],
        "volume": [bar.volume for bar in bars],
        "has_control_bar": [
            bar.prop.get("ControlBar") is not None if bar.prop else False
            for bar in bars
        ],
    }

    df = pd.DataFrame(data)
    df["datetime"] = pd.to_datetime(df["datetime"])

    return df, bars


def calculate_weekly_bars(bars: List[Bar]):
    """Calculate weekly aggregated bars positioned on Saturdays
    Returns: (weekly_df, weekly_bars_dict, weekly_bar_objects) where:
        - weekly_df: DataFrame for charting
        - weekly_bars_dict: maps saturday datetime to list of daily bars
        - weekly_bar_objects: List of Bar objects for weekly bars with indicators applied
    """
    from datetime import timedelta

    if not bars:
        return pd.DataFrame(), {}, []

    # Group bars by week (Monday-Friday)
    weekly_bars = {}

    for bar in bars:
        bar_date = bar.time.date()
        weekday = bar_date.weekday()

        # Calculate Monday of this week
        days_to_monday = weekday
        monday = bar_date - timedelta(days=days_to_monday)

        # Saturday is the key for this week
        saturday = monday + timedelta(days=5)

        if saturday not in weekly_bars:
            weekly_bars[saturday] = []
        weekly_bars[saturday].append(bar)

    # Aggregate each week's data and create Bar objects
    weekly_data = []
    weekly_bars_with_datetime = {}  # Map saturday_datetime to bars list
    weekly_bar_objects = []  # List of Bar objects for weekly bars

    for week_idx, (saturday, week_bars) in enumerate(sorted(weekly_bars.items())):
        if week_bars:
            # Position weekly bar at Saturday noon (mid of Saturday and Sunday)
            saturday_datetime = pd.Timestamp.combine(
                saturday, pd.Timestamp("12:00:00").time()
            )

            # If original bars have timezone, preserve it
            last_bar_time = week_bars[-1].time
            if hasattr(last_bar_time, "tzinfo") and last_bar_time.tzinfo is not None:
                saturday_datetime = saturday_datetime.replace(
                    tzinfo=last_bar_time.tzinfo
                )

            open_price = week_bars[0].open
            high_price = max(b.high for b in week_bars)
            low_price = min(b.low for b in week_bars)
            close_price = week_bars[-1].close
            volume = sum(b.volume for b in week_bars)

            weekly_data.append(
                {
                    "datetime": saturday_datetime,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                }
            )
            weekly_bars_with_datetime[saturday_datetime] = week_bars

            # Create Bar object for weekly bar
            weekly_bar = Bar(
                time=saturday_datetime,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
                idx=week_idx,
            )
            weekly_bar_objects.append(weekly_bar)

    if not weekly_data:
        return pd.DataFrame(), {}, []

    # Apply indicators to weekly bars
    if weekly_bar_objects:
        from indicators import (
            BasicIndicators,
            BarStructIndicator,
            LastWeekBreakIndicator,
            MovementIndicator,
            EffortPaceIndicator,
            TalibPatternsIndicator,
            MyTrendIndicator,
        )

        # Apply indicators (same as main_struct.py for consistency)
        indicators = [
            BasicIndicators(),
            LastWeekBreakIndicator(),
            BarStructIndicator(),
            MovementIndicator(),
            EffortPaceIndicator(),
            TalibPatternsIndicator(),
            MyTrendIndicator(),
        ]

        for indicator in indicators:
            indicator.apply(weekly_bar_objects)

    df = pd.DataFrame(weekly_data)
    df["datetime"] = pd.to_datetime(df["datetime"])

    return df, weekly_bars_with_datetime, weekly_bar_objects
