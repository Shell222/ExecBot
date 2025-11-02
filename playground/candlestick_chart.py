from typing import List, Optional
import pandas as pd
from datetime import datetime
import time
from bokeh.plotting import figure, show, save
from bokeh.models import HoverTool, DatetimeTickFormatter
from bokeh.io import output_file, curdoc
from bokeh.server.server import Server
from bokeh.application import Application
from bokeh.application.handlers import FunctionHandler
from bokeh.layouts import column
from bokeh.models import ColumnDataSource
import threading
import webbrowser
from loguru import logger

from bar import Bar, TvClient
from zigzag import Zigzag, Pivot
from tvDatafeed import Interval


class CandlestickChartServer:
    """
    A Bokeh chart server class to display bars as candlesticks with optional zigzag pivots.
    Can periodically fetch new data from TradingView using TvClient.
    """

    def __init__(
        self,
        port=5006,
        title="Candlestick Chart",
        symbol: str = "TSLA",
        exchange: str = "NASDAQ",
        interval: Interval = Interval.in_30_minute,
        n_bars: int = 200,
        update_interval_seconds: int = None,
        zigzag_pct_change: float = 3.0,
    ):
        self.port = port
        self.title = title
        self.bars: List[Bar] = []
        self.pivots: List[Pivot] = []
        self.server = None
        self.thread = None

        # Data fetching parameters
        self.symbol = symbol
        self.exchange = exchange
        self.interval = interval
        self.n_bars = n_bars
        self.update_interval_seconds = update_interval_seconds
        self.zigzag_pct_change = zigzag_pct_change

        # TradingView client and zigzag calculator
        self.tv_client: TvClient = TvClient()
        self.zigzag: Zigzag = Zigzag(pct_change=zigzag_pct_change)

        # Update thread management
        self.update_thread = None
        self.stop_updates = False

        # Plot references for real-time updates
        self.main_data_source = None
        self.pivot_data_source = None
        self.green_wick_source = None
        self.red_wick_source = None
        self.green_body_source = None
        self.red_body_source = None

        # Fetch initial data
        self._fetch_initial_data()

    def _handle_bar(self, bar: Bar) -> bool:
        """
        Handle a new bar by updating zigzag and data structures.

        Args:
            bar: The new Bar object to process

        Returns:
            bool: True if the bar was processed (new), False if it was a duplicate
        """
        # Check if this bar already exists (avoid duplicates)
        if self.bars and bar.time <= self.bars[-1].time:
            return False

        # Add the bar to our collection
        self.bars.append(bar)

        # Update zigzag if configured
        self.zigzag.HandleBar(bar)
        self.pivots = self.zigzag.pivots

        # Update the plots with append mode for efficiency
        self._update_plot_data(append_mode=True)

        return True

    def _update_plot_data(self, append_mode: bool = False):
        """
        Update the plot data sources with current bar and pivot data.

        Args:
            append_mode: If True, only append the latest bar data. If False, replace all data.
        """
        if not self.main_data_source:
            return  # Plot not yet created

        try:
            if append_mode and len(self.bars) > 0:
                # Only append the latest bar
                self._append_latest_bar()
            else:
                # Replace all data (initial load or full refresh)
                self._replace_all_data()

            # Update zigzag pivots using the new method
            plot_sources = {"pivot_data_source": self.pivot_data_source}
            self.zigzag.update_plot_sources(plot_sources, self.bars)

            logger.debug("Plot data updated")

        except Exception as e:
            logger.error(f"Error updating plot data: {e}")

    def _append_latest_bar(self):
        """Append only the latest bar to the plot data sources."""
        if not self.bars:
            return

        latest_bar = self.bars[-1]

        # Calculate plot index for the latest bar
        plot_index = len(self.bars) - 1

        # Prepare data for the latest bar
        bar_data = {
            "datetime": [latest_bar.time],
            "plot_index": [plot_index],
            "open": [latest_bar.open],
            "high": [latest_bar.high],
            "low": [latest_bar.low],
            "close": [latest_bar.close],
            "volume": [latest_bar.volume],
        }

        # Append to main data source
        for key, values in bar_data.items():
            if key in self.main_data_source.data:
                self.main_data_source.data[key].extend(values)
            else:
                self.main_data_source.data[key] = values

        # Determine candle color and append to appropriate sources
        is_green = latest_bar.close >= latest_bar.open

        if is_green:
            # Append to green sources, add empty data to red sources
            for source in [self.green_wick_source, self.green_body_source]:
                if source:
                    for key, values in bar_data.items():
                        if key in source.data:
                            source.data[key].extend(values)
                        else:
                            source.data[key] = values

            # Add placeholder data to red sources to maintain alignment
            for source in [self.red_wick_source, self.red_body_source]:
                if source:
                    for key in bar_data.keys():
                        if key in source.data:
                            source.data[key].extend([None])
                        else:
                            source.data[key] = [None]
        else:
            # Append to red sources, add empty data to green sources
            for source in [self.red_wick_source, self.red_body_source]:
                if source:
                    for key, values in bar_data.items():
                        if key in source.data:
                            source.data[key].extend(values)
                        else:
                            source.data[key] = values

            # Add placeholder data to green sources to maintain alignment
            for source in [self.green_wick_source, self.green_body_source]:
                if source:
                    for key in bar_data.keys():
                        if key in source.data:
                            source.data[key].extend([None])
                        else:
                            source.data[key] = [None]

    def _replace_all_data(self):
        """Replace all data in the plot data sources."""
        # Prepare updated data
        df = self._prepare_data()

        if df.empty:
            return

        # Update main data source
        self.main_data_source.data = df

        # Separate data for green and red candles
        inc = df["close"] >= df["open"]
        dec = df["close"] < df["open"]

        # Update candle data sources
        if self.green_wick_source:
            self.green_wick_source.data = ColumnDataSource(df[inc]).data
        if self.red_wick_source:
            self.red_wick_source.data = ColumnDataSource(df[dec]).data
        if self.green_body_source:
            self.green_body_source.data = ColumnDataSource(df[inc]).data
        if self.red_body_source:
            self.red_body_source.data = ColumnDataSource(df[dec]).data

    def _fetch_initial_data(self):
        """Fetch initial bar data and calculate zigzag pivots."""
        try:
            logger.info(f"Fetching initial data for {self.symbol} ({self.exchange})")
            initial_bars = self.tv_client.get_bars(
                symbol=self.symbol,
                exchange=self.exchange,
                interval=self.interval,
                n_bars=self.n_bars,
            )

            # Process all bars without updating plots for efficiency
            self.bars = []  # Start fresh
            for bar in initial_bars:
                # Add the bar and update zigzag without plot updates
                self.bars.append(bar)
                self.zigzag.HandleBar(bar)

            self.pivots = self.zigzag.pivots

            # Now update all plot data at once for initial load
            self._update_plot_data(append_mode=False)

            logger.info(f"Fetched {len(self.bars)} bars and {len(self.pivots)} pivots")

        except Exception as e:
            logger.error(f"Error fetching initial data: {e}")
            self.bars = []
            self.pivots = []

    def _fetch_new_data(self):
        """Fetch new bar data and update zigzag pivots."""
        try:
            # Fetch latest bars (get a few extra to catch any updates)
            new_bars = self.tv_client.get_bars(
                symbol=self.symbol,
                exchange=self.exchange,
                interval=self.interval,
                n_bars=min(10, self.n_bars),  # Get last 10 bars or n_bars if smaller
            )

            if not new_bars:
                return

            # Process new bars through the handler
            new_bar_count = 0
            for bar in new_bars:
                if self._handle_bar(bar):
                    new_bar_count += 1

            logger.info(
                f"Added {new_bar_count} new bars. Total: {len(self.bars)} bars, {len(self.pivots)} pivots"
            )

        except Exception as e:
            logger.error(f"Error fetching new data: {e}")

    def _update_data_loop(self):
        """Background loop to periodically fetch new data."""
        while not self.stop_updates:
            self._fetch_new_data()
            time.sleep(self.update_interval_seconds)

    def start_data_updates(self):
        """Start the background data update thread."""
        if self.update_interval_seconds and self.symbol:
            self.stop_updates = False
            self.update_thread = threading.Thread(
                target=self._update_data_loop, daemon=True
            )
            self.update_thread.start()
            logger.info(
                f"Started data updates every {self.update_interval_seconds} seconds"
            )

    def stop_data_updates(self):
        """Stop the background data update thread."""
        self.stop_updates = True
        if self.update_thread:
            self.update_thread.join(timeout=1)
            logger.info("Stopped data updates")

    def _prepare_data(self):
        """Convert Bar objects to pandas DataFrame for Bokeh."""
        if not self.bars:
            return pd.DataFrame()

        data = {
            "datetime": [bar.time for bar in self.bars],
            "open": [bar.open for bar in self.bars],
            "high": [bar.high for bar in self.bars],
            "low": [bar.low for bar in self.bars],
            "close": [bar.close for bar in self.bars],
            "volume": [bar.volume for bar in self.bars],
        }

        df = pd.DataFrame(data)

        # Add continuous index for plotting (no gaps)
        df["plot_index"] = range(len(df))

        # Calculate colors for candles
        df["color"] = [
            "green" if close >= open else "red"
            for close, open in zip(df["close"], df["open"])
        ]

        # Calculate candle body dimensions
        df["body_top"] = df[["open", "close"]].max(axis=1)
        df["body_bottom"] = df[["open", "close"]].min(axis=1)
        df["body_height"] = df["body_top"] - df["body_bottom"]

        return df

    def _create_plot(self, doc):
        """Create the Bokeh plot."""
        df = self._prepare_data()

        if df.empty:
            logger.warning("No data available for plotting")
            return

        # Create figure (remove x_axis_type="datetime" to use continuous index)
        p = figure(
            title=self.title,
            width=1200,
            height=600,
            tools="pan,wheel_zoom,box_zoom,reset,save",
            active_scroll="wheel_zoom",
        )

        # Create data source and store reference for updates
        source = ColumnDataSource(df)
        self.main_data_source = source

        # Separate data for green and red candles
        inc = df["close"] >= df["open"]  # Green candles
        dec = df["close"] < df["open"]  # Red candles

        # Width for candle bodies (continuous index, so 1.0 = 1 bar width)
        w = 0.8  # 80% of bar spacing for bodies

        candlestick_renderers = []

        # Green candle wicks (using vbar instead of segment) - store reference
        green_wick_source = ColumnDataSource(df[inc])
        self.green_wick_source = green_wick_source
        green_wick_renderer = p.vbar(
            x="plot_index",
            width=w * 0.05,  # Very thin width for wick appearance
            top="high",
            bottom="low",
            source=green_wick_source,
            fill_color="#05F705",  # deep green for green candles
            line_color="#05F705",
            line_width=1,
        )
        candlestick_renderers.append(green_wick_renderer)

        # Red candle wicks (using vbar instead of segment) - store reference
        red_wick_source = ColumnDataSource(df[dec])
        self.red_wick_source = red_wick_source
        red_wick_renderer = p.vbar(
            x="plot_index",
            width=w * 0.05,  # Very thin width for wick appearance
            top="high",
            bottom="low",
            source=red_wick_source,
            fill_color="#EC0808",  # deep red for red candles
            line_color="#EC0808",
            line_width=1,
        )
        candlestick_renderers.append(red_wick_renderer)

        # Green candle bodies - store reference
        green_body_source = ColumnDataSource(df[inc])
        self.green_body_source = green_body_source
        green_body_renderer = p.vbar(
            x="plot_index",
            width=w,
            top="close",
            bottom="open",
            source=green_body_source,
            fill_color="#00CC00",
            line_color="#00CC00",
            line_alpha=0.3,
        )
        candlestick_renderers.append(green_body_renderer)

        # Red candle bodies - store reference
        red_body_source = ColumnDataSource(df[dec])
        # Red candle bodies - store reference
        red_body_source = ColumnDataSource(df[dec])
        self.red_body_source = red_body_source
        red_body_renderer = p.vbar(
            x="plot_index",
            width=w,
            top="open",
            bottom="close",
            source=red_body_source,
            fill_color="#FF3333",
            line_color="#FF3333",
            line_alpha=0.3,
        )
        candlestick_renderers.append(red_body_renderer)

        # Get pivot data from zigzag
        pivot_df = self.zigzag.get_plot_data(self.bars)

        # Add pivot points if available
        if not pivot_df.empty:
            pivot_source = ColumnDataSource(pivot_df)
            self.pivot_data_source = pivot_source  # Store reference

            # Add pivot points as scatter plot
            p.scatter(
                x="plot_index",
                y="price",
                source=pivot_source,
                size=8,
                color="color",
                alpha=0.8,
                legend_label="Zigzag Pivots",
            )

            # Connect pivot points with lines
            if len(pivot_df) > 1:
                p.line(
                    x="plot_index",
                    y="price",
                    source=pivot_source,
                    line_width=2,
                    color="purple",
                    alpha=0.7,
                    legend_label="Zigzag Lines",
                )

        # Configure hover tool for candle bodies (which have the complete data)
        hover = HoverTool(
            tooltips=[
                ("Date", "@datetime{%F %T}"),
                ("Open", "@open{0.00}"),
                ("High", "@high{0.00}"),
                ("Low", "@low{0.00}"),
                ("Close", "@close{0.00}"),
                ("Volume", "@volume{0,0}"),
            ],
            formatters={"@datetime": "datetime"},
            renderers=[green_body_renderer, red_body_renderer],
        )
        p.add_tools(hover)

        # Format axes with custom datetime labels
        # Create a mapping from index to datetime string for major ticks
        datetime_labels = {}
        step = max(1, len(df) // 10)  # Show roughly 10 labels
        for i in range(0, len(df), step):
            datetime_labels[i] = df.iloc[i]["datetime"].strftime("%m/%d %H:%M")

        # Add the last point if not already included
        if len(df) - 1 not in datetime_labels:
            datetime_labels[len(df) - 1] = df.iloc[-1]["datetime"].strftime(
                "%m/%d %H:%M"
            )

        # Set major ticks and labels
        p.xaxis.ticker = list(datetime_labels.keys())
        p.xaxis.major_label_overrides = datetime_labels

        p.yaxis.axis_label = "Price"
        p.xaxis.axis_label = "Time"

        # Configure legend
        if len(self.pivots) > 0:
            p.legend.location = "top_left"
            p.legend.click_policy = "hide"

        # Add to document
        doc.add_root(column(p))
        doc.title = self.title

    def start_server(self, show_browser=True):
        """Start the Bokeh server and optionally start data updates."""

        def modify_doc(doc):
            self._create_plot(doc)

        # Create application
        app = Application(FunctionHandler(modify_doc))

        # Start server
        self.server = Server(
            {"/": app},
            port=self.port,
            allow_websocket_origin=["localhost:{}".format(self.port)],
        )
        self.server.start()

        logger.info(f"Bokeh server started at http://localhost:{self.port}")

        if show_browser:
            # Open browser
            webbrowser.open(f"http://localhost:{self.port}")

        # Run server in background thread
        def run_server():
            self.server.io_loop.start()

        self.thread = threading.Thread(target=run_server, daemon=True)
        self.thread.start()

        # Start data updates if configured
        if self.update_interval_seconds:
            self.start_data_updates()

        return f"http://localhost:{self.port}"

    def stop_server(self):
        """Stop the Bokeh server and data updates."""
        # Stop data updates first
        self.stop_data_updates()

        if self.server:
            self.server.stop()
            self.server = None
            logger.info("Bokeh server stopped")


def create_live_chart(
    symbol: str,
    exchange: str,
    interval: Interval,
    title: Optional[str] = None,
    port=5006,
    n_bars=200,
    update_interval_seconds: Optional[int] = None,
    zigzag_pct_change: Optional[float] = None,
):
    """
    Convenience function to create a live-updating chart server that fetches data from TradingView.

    Args:
        symbol: Trading symbol (e.g., "TSLA")
        exchange: Exchange name (e.g., "NASDAQ")
        interval: Time interval for bars (e.g., Interval.in_30_minute)
        title: Chart title (auto-generated if None)
        port: Server port
        n_bars: Number of bars to keep in memory
        update_interval_seconds: Seconds between data updates (None = no updates)
        zigzag_pct_change: Percentage change for zigzag pivots (None = no zigzag)

    Returns:
        CandlestickChartServer instance
    """
    if title is None:
        interval_str = str(interval).split(".")[-1] if interval else "unknown"
        zigzag_str = f" with {zigzag_pct_change}% Zigzag" if zigzag_pct_change else ""
        title = f"{symbol} {interval_str} Candlesticks{zigzag_str}"

    chart_server = CandlestickChartServer(
        port=port,
        title=title,
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        n_bars=n_bars,
        update_interval_seconds=update_interval_seconds,
        zigzag_pct_change=zigzag_pct_change,
    )

    url = chart_server.start_server(show_browser=True)

    logger.info(f"Live chart server running at {url}")
    if update_interval_seconds:
        logger.info(f"Data updates every {update_interval_seconds} seconds")
    logger.info("Press Ctrl+C to stop the server")

    return chart_server


if __name__ == "__main__":

    # Approach 2: Live chart with automatic data updates
    chart_server = create_live_chart(
        symbol="TSLA",
        exchange="NASDAQ",
        interval=Interval.in_30_minute,
        n_bars=2000,
        update_interval_seconds=None,
        zigzag_pct_change=3.0,  # 3% zigzag
        port=5006,
    )

    try:
        # Keep the server running
        input("Press Enter to stop the server...\n")
    except KeyboardInterrupt:
        pass
    finally:
        chart_server.stop_server()
