"""
Streamlit UI for Stock Data Analysis Application

This application provides a web interface for the stock analysis tool,
displaying candlestick data, technical indicators, and trading signals.
"""

from loguru import logger
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import os
from typing import List, Dict, Optional
import streamlit.components.v1 as components
from bokeh.embed import file_html
from bokeh.resources import CDN

from main_struct import StockAnalyzer
from tvDatafeed import Interval
from playground.bar import Bar
from bokeh_charts import create_bokeh_candlestick_chart

# Configure loguru to write logs to file
logger.add(
    "log.txt",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    backtrace=True,
    diagnose=True,
)

logger.info("Streamlit application started")


def init_session_state():
    """Initialize session state variables"""
    if "analyzer" not in st.session_state:
        st.session_state.analyzer = None
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None
    if "bars_data" not in st.session_state:
        st.session_state.bars_data = None


def get_analyzer(num_recent_bars: int = 20):
    """Get or create StockAnalyzer instance"""
    if (
        st.session_state.analyzer is None
        or getattr(st.session_state.analyzer, "num_recent_bars", None)
        != num_recent_bars
    ):
        st.session_state.analyzer = StockAnalyzer(num_recent_bars=num_recent_bars)
    return st.session_state.analyzer


def create_candlestick_chart(
    bars_data: pd.DataFrame,
    recent_bars: List[Bar] = None,
    normalized_bars: List[Bar] = None,
):
    """Create an interactive Bokeh candlestick chart for Streamlit with built-in controls"""
    from bokeh_charts import calculate_weekly_bars

    # Calculate weekly data from all bars
    weekly_data = None
    weekly_bars_dict = None
    weekly_bars = None
    if recent_bars:
        weekly_data, weekly_bars_dict, weekly_bars = calculate_weekly_bars(recent_bars)

    # Calculate normalized weekly data from normalized bars
    normalized_weekly_data = None
    normalized_weekly_bars_dict = None
    normalized_weekly_bars = None
    if normalized_bars:
        normalized_weekly_data, normalized_weekly_bars_dict, normalized_weekly_bars = (
            calculate_weekly_bars(normalized_bars)
        )

    # Convert normalized bars to DataFrame
    normalized_bars_data = None
    if normalized_bars:
        normalized_data = []
        for bar in normalized_bars:
            normalized_data.append(
                {
                    "datetime": bar.time,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
            )
        normalized_bars_data = pd.DataFrame(normalized_data)
        normalized_bars_data["datetime"] = pd.to_datetime(
            normalized_bars_data["datetime"]
        )

    # Pass full data - controls are handled by Bokeh widgets
    chart = create_bokeh_candlestick_chart(
        bars_data,
        title="Stock Price Chart",
        weekly_data=weekly_data,
        show_dots=True,
        full_bars_data=bars_data,
        weekly_bars_dict=weekly_bars_dict,
        bars=recent_bars,
        weekly_bars=weekly_bars,
        normalized_bars_data=normalized_bars_data,
        normalized_weekly_data=normalized_weekly_data,
        normalized_bars=normalized_bars,
        normalized_weekly_bars=normalized_weekly_bars,
    )
    return chart


def display_bokeh_chart(bokeh_figure, height: int = 850):
    """Display Bokeh chart in Streamlit using components.html"""
    html = file_html(bokeh_figure, CDN, "Candlestick Chart")
    components.html(html, height=height, scrolling=False)


def display_recent_bars_table(recent_bars: List[Bar]):
    """Display recent bars in a timeline table format"""
    if not recent_bars:
        st.warning("No recent bars data available")
        return

    # Convert Bar objects to DataFrame for display
    bars_data = []
    for bar in recent_bars:
        bar_data = {
            "date": bar.time.strftime("%Y-%m-%d"),
            "movement_type": bar.prop.get("movement_type", "") if bar.prop else "",
            "std_price_delta": bar.prop.get("std_price_delta", 0) if bar.prop else 0,
            "patterns": bar.prop.get("detected_patterns", []) if bar.prop else [],
        }
        bars_data.append(bar_data)

    df = pd.DataFrame(bars_data)

    # Select and order the data we want to display
    selected_df = df[
        [
            "date",
            "movement_type",
            "std_price_delta",
            "patterns",
        ]
    ].copy()

    # Round numeric values
    selected_df["std_price_delta"] = selected_df["std_price_delta"].round(4)

    # Format patterns column
    selected_df["patterns"] = selected_df["patterns"].apply(
        lambda x: ", ".join(x[:2]) if x else ""  # Show max 2 patterns to save space
    )

    # Create timeline format - transpose and set dates as columns
    timeline_df = selected_df.set_index("date").T

    # Ensure columns are in chronological order (oldest to newest, left to right)
    timeline_df = timeline_df.reindex(sorted(timeline_df.columns), axis=1)

    # Create row labels with better formatting
    row_labels = {
        "movement_type": "Movement",
        "std_price_delta": "Std Delta",
        "patterns": "Patterns",
    }

    timeline_df.index = timeline_df.index.map(lambda x: row_labels.get(x, x))

    st.dataframe(
        timeline_df,
        use_container_width=True,
    )


def create_timeline_visualization(recent_bars: List[Bar]):
    """Create a native vis.js timeline visualization for stock events"""
    if not recent_bars:
        st.warning("No data available for timeline")
        return

    # Prepare timeline events
    timeline_events = []
    groups = []

    # Define groups
    groups = [
        {"id": "movement", "content": "Move"},
        {"id": "alt_movement", "content": "Alt Move"},
        {"id": "outer_movement", "content": "Outer Move"},
        {"id": "last_week_break", "content": "Week Break"},
        {"id": "is_controlled", "content": "Controlled"},
        {"id": "patterns", "content": "Patterns"},
    ]

    # Collect movement colors for CSS generation
    movement_colors = {}
    alter_movement_colors = {}
    outer_movement_colors = {}

    for i, bar in enumerate(recent_bars):
        date_str = bar.time.strftime("%Y-%m-%d")
        # Calculate end time (12 hours later)
        start_date = datetime.strptime(date_str, "%Y-%m-%d")
        mid_date = start_date + timedelta(hours=12)
        end_date = start_date + timedelta(hours=24)
        start_iso = start_date.isoformat()
        mid_iso = mid_date.isoformat()
        end_iso = end_date.isoformat()

        # Create event for significant movements
        movement_type = bar.prop.get("movement_type", "") if bar.prop else ""
        movement_score = bar.prop.get("movement_score", 0) if bar.prop else 0
        alter_movement_score = (
            bar.prop.get("alter_movement_score", 0) if bar.prop else 0
        )
        outer_movement_score = (
            bar.prop.get("outer_movement_score", 0) if bar.prop else 0
        )
        movement_color = (
            bar.prop.get("movement_color", "#6c757d") if bar.prop else "#6c757d"
        )
        alter_movement_color = (
            bar.prop.get("alter_movement_color", "#6c757d") if bar.prop else "#6c757d"
        )
        outer_movement_color = (
            bar.prop.get("outer_movement_color", "#6c757d") if bar.prop else "#6c757d"
        )
        logger.info(
            f"Bar {i}: movement_type={movement_type}, movement_score={movement_score:.2f}, movement_color={movement_color}"
        )
        if movement_type and movement_type != "neutral":
            class_name = f"movement-{i}"
            alter_class_name = f"alt-movement-{i}"
            outer_class_name = f"outer-movement-{i}"
            movement_colors[class_name] = movement_color
            alter_movement_colors[alter_class_name] = alter_movement_color
            outer_movement_colors[outer_class_name] = outer_movement_color

            timeline_events.append(
                {
                    "id": f"movement_{i}",
                    "content": f"{movement_score:.1f}",
                    "start": start_iso,
                    "end": end_iso,
                    "group": "movement",
                    "className": class_name,
                }
            )

            # Add alternative movement score event
            timeline_events.append(
                {
                    "id": f"alt_movement_{i}",
                    "content": f"{alter_movement_score:.1f}",
                    "start": start_iso,
                    "end": end_iso,
                    "group": "alt_movement",
                    "className": alter_class_name,
                }
            )

            # Add outer movement score event
            timeline_events.append(
                {
                    "id": f"outer_movement_{i}",
                    "content": f"{outer_movement_score:.1f}",
                    "start": start_iso,
                    "end": end_iso,
                    "group": "outer_movement",
                    "className": outer_class_name,
                }
            )

        # Create event for last week break
        last_week_break = bar.prop.get("last_week_break") if bar.prop else None
        if last_week_break:
            break_class = (
                "break-upside" if last_week_break == "upside" else "break-downside"
            )
            break_content = "W⬆️" if last_week_break == "upside" else "W⬇️"
            timeline_events.append(
                {
                    "id": f"week_break_{i}",
                    "content": break_content,
                    "start": mid_iso,
                    "point": True,
                    "group": "last_week_break",
                    "className": break_class,
                }
            )

        # Create event for controlled bars
        has_control_bar = bar.prop.get("ControlBar") is not None if bar.prop else False
        if has_control_bar:
            timeline_events.append(
                {
                    "id": f"controlled_{i}",
                    "content": "C",
                    "start": start_iso,
                    "end": end_iso,
                    "group": "is_controlled",
                    "className": "controlled-bar",
                }
            )

        # Create events for detected patterns
        patterns = bar.prop.get("detected_patterns", []) if bar.prop else []
        for j, pattern in enumerate(patterns):
            timeline_events.append(
                {
                    "id": f"pattern_{i}_{j}",
                    "content": pattern.replace("_", " ").title(),
                    "start": mid_iso,
                    "point": True,
                    "group": "patterns",
                    "className": "pattern-event",
                }
            )

    if not timeline_events:
        st.info("No significant events to display on timeline")
        return

    # Generate dynamic CSS for movement colors
    movement_css = ""
    for class_name, color in movement_colors.items():
        movement_css += f"""
            .vis-item.{class_name} {{
                background-color: {color};
                border-color: {color};
                color: white;
            }}
        """

    # Generate dynamic CSS for alternative movement colors
    for class_name, color in alter_movement_colors.items():
        movement_css += f"""
            .vis-item.{class_name} {{
                background-color: {color};
                border-color: {color};
                color: white;
            }}
        """

    # Generate dynamic CSS for outer movement colors
    for class_name, color in outer_movement_colors.items():
        movement_css += f"""
            .vis-item.{class_name} {{
                background-color: {color};
                border-color: {color};
                color: white;
            }}
        """

    # Create the HTML with vis-timeline
    timeline_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Stock Analysis Timeline</title>
        <script type="text/javascript" src="https://unpkg.com/vis-timeline@latest/standalone/umd/vis-timeline-graph2d.min.js"></script>
        <link href="https://unpkg.com/vis-timeline@latest/styles/vis-timeline-graph2d.min.css" rel="stylesheet" type="text/css" />
        <style type="text/css">
            #timeline {{
                width: 100%;
                height: 400px;
                border: 1px solid lightgray;
            }}
            
            {movement_css}
            
            .vis-item.pattern-event {{
                background-color: #007bff;
                border-color: #0056b3;
                color: white;
            }}
            
            .vis-item.break-upside {{
                background-color: #28a745;
                border-color: #1e7e34;
                color: white;
                font-weight: bold;
            }}
            
            .vis-item.break-downside {{
                background-color: #dc3545;
                border-color: #bd2130;
                color: white;
                font-weight: bold;
            }}
            
            .vis-item.controlled-bar {{
                background-color: #6c757d;
                border-color: #5a6268;
                color: white;
                opacity: 0.6;
            }}
        </style>
    </head>
    <body>
        <div id="timeline"></div>

        <script type="text/javascript">
            // Create a DataSet (allows two way data-binding)
            var items = new vis.DataSet({json.dumps(timeline_events)});
            
            // Create a DataSet for groups
            var groups = new vis.DataSet({json.dumps(groups)});

            // Configuration for the Timeline
            var options = {{
                width: '100%',
                height: '300px',
                margin: {{
                    item: 10,
                    axis: 40
                }},
                orientation: 'top',
                stack: false,
                showCurrentTime: false,
                zoomMin: 1000 * 60 * 60 * 24,     // one day in milliseconds
                zoomMax: 1000 * 60 * 60 * 24 * 31 * 12, // about a year in milliseconds
            }};

            // Create a Timeline
            var container = document.getElementById('timeline');
            var timeline = new vis.Timeline(container, items, groups, options);
        </script>
    </body>
    </html>
    """

    # Display the timeline
    components.html(timeline_html, height=450)


def display_trading_signals(signals: Dict):
    """Display trading signals in an organized way"""
    if not signals:
        st.warning("No trading signals available")
        return

    # Display signal type with colored badge
    signal_type = signals.get("signal_type", "neutral").upper()

    if signal_type == "BUY":
        st.success(f"📈 **Signal: {signal_type}**")
    elif signal_type == "SELL":
        st.error(f"📉 **Signal: {signal_type}**")
    else:
        st.info(f"📊 **Signal: {signal_type}**")

    # Display confidence if available
    if "confidence" in signals:
        confidence = signals["confidence"]
        st.metric("Confidence Level", f"{confidence}%")

    # Display reasoning
    if "reasoning" in signals:
        st.subheader("Analysis Reasoning")
        st.write(signals["reasoning"])

    # Display recommendations
    if "recommendations" in signals:
        st.subheader("Recommendations")
        for rec in signals["recommendations"]:
            st.write(f"• {rec}")


def main():
    st.set_page_config(
        page_title="Stock Analysis Dashboard",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init_session_state()

    st.title("📈 Stock Analysis Dashboard")
    st.markdown(
        "Analyze stock data with technical indicators and AI-powered trading signals"
    )

    # Sidebar for input parameters
    st.sidebar.header("Analysis Parameters")

    # Stock selection
    symbol = st.sidebar.text_input(
        "Stock Symbol", value="TSLA", help="Enter stock symbol (e.g., TSLA, AAPL)"
    )
    exchange = st.sidebar.selectbox(
        "Exchange", options=["NASDAQ", "NYSE", "AMEX"], index=0
    )

    # Fixed to daily interval
    interval = Interval.in_daily
    interval_str = "1 Day"

    # Number of bars
    n_bars = st.sidebar.slider(
        "Number of Bars", min_value=50, max_value=1000, value=500
    )

    # Number of recent bars to analyze
    num_recent_bars = st.sidebar.slider(
        "Recent Bars to Analyze",
        min_value=5,
        max_value=500,
        value=500,
        help="Number of most recent bars to display and analyze",
    )

    # Analysis button
    if st.sidebar.button("🚀 Run Analysis", type="primary"):
        with st.spinner("Analyzing stock data..."):
            try:
                analyzer = get_analyzer(num_recent_bars)

                # Run the analysis
                result = analyzer.analyze_stock_main(symbol, exchange, interval, n_bars)
                st.session_state.analysis_result = result

                # Convert recent bars to DataFrame for charts
                if "recent_bars" in result:
                    bars = result["recent_bars"]
                    bars_data = []
                    for bar in bars:
                        bars_data.append(
                            {
                                "datetime": bar.time,
                                "open": bar.open,
                                "high": bar.high,
                                "low": bar.low,
                                "close": bar.close,
                                "volume": bar.volume,
                                "has_control_bar": (
                                    bar.prop.get("ControlBar") is not None
                                    if bar.prop
                                    else False
                                ),
                            }
                        )
                    st.session_state.bars_data = pd.DataFrame(bars_data)
                    st.session_state.bars_data["datetime"] = pd.to_datetime(
                        st.session_state.bars_data["datetime"]
                    )

                st.success("Analysis completed successfully!")

            except Exception as e:
                st.error(f"Analysis failed: {str(e)}")
                return

    # Display results if available
    if st.session_state.analysis_result is not None:
        result = st.session_state.analysis_result
        bars_data = st.session_state.bars_data

        # Charts section
        if bars_data is not None and not bars_data.empty:
            st.header("📈 Price Charts")

            # Candlestick chart
            candlestick_chart = create_candlestick_chart(
                bars_data,
                result["recent_bars"],
                result.get("normalized_bars", []),
            )
            display_bokeh_chart(
                candlestick_chart, height=1200
            )  # Increased height for two charts

        # Recent bars table
        if "recent_bars" in result:
            st.header("📋 Recent Bars Data")

            # Timeline visualization
            st.subheader("🕒 Timeline Visualization")
            create_timeline_visualization(result["recent_bars"])

            st.subheader("📊 Data Table")

            # Filter options
            col1, col2 = st.columns(2)
            with col1:
                show_all = st.checkbox("Show all bars", value=False)
            with col2:
                if not show_all:
                    num_bars_display = st.slider(
                        "Number of recent bars to display",
                        min_value=5,
                        max_value=500,
                        value=200,
                    )
                else:
                    num_bars_display = len(result["recent_bars"])

            recent_bars_to_show = (
                result["recent_bars"][-num_bars_display:]
                if not show_all
                else result["recent_bars"]
            )
            display_recent_bars_table(recent_bars_to_show)

    else:
        st.info(
            "👆 Configure parameters in the sidebar and click 'Run Analysis' to start."
        )

    # Footer
    st.markdown("---")
    st.markdown("Built with ❤️ using Streamlit and powered by Claude AI")


if __name__ == "__main__":
    main()
