# Candlestick Chart Server

A comprehensive Bokeh-based candlestick chart server for displaying financial data with optional zigzag pivot analysis.

## Features

- **Interactive Candlestick Charts**: Real-time candlestick visualization with pan, zoom, and hover capabilities
- **Zigzag Pivot Analysis**: Overlay zigzag pivots to identify significant price movements
- **Static Chart Export**: Save charts as standalone HTML files
- **Multiple Timeframes**: Support for various timeframes (5min, 15min, 30min, 1hour, 4hour, etc.)
- **Professional Styling**: Green/red candles, customizable colors, and clean layouts
- **Hover Information**: Detailed OHLCV data on hover
- **Web-based Server**: Background server for interactive charts

## Quick Start

### Basic Usage

```python
from candlestick_chart import CandlestickChartServer, create_chart_from_bars
from bar import GetBarsForSymbol
from tvDatafeed import Interval

# Fetch data
bars = GetBarsForSymbol("TSLA", "NASDAQ", Interval.in_30_minute, 100)

# Create interactive chart
chart_server = create_chart_from_bars(
    bars=bars,
    title="TSLA 30min Candlesticks",
    port=5006
)

# Keep server running
input("Press Enter to stop...")
chart_server.stop_server()
```

### With Zigzag Analysis

```python
from zigzag import Zigzag

# Calculate zigzag pivots
zigzag = Zigzag(pct_change=3)  # 3% threshold
for bar in bars:
    zigzag.HandleBar(bar)

# Create chart with zigzag overlay
chart_server = create_chart_from_bars(
    bars=bars,
    pivots=zigzag.pivots,
    title="TSLA with Zigzag Analysis"
)
```

### Static Chart Export

```python
chart_server = CandlestickChartServer(title="Static Chart")
chart_server.set_data(bars, pivots)
chart_server.save_static_chart("my_chart.html")
```

## Class Reference

### CandlestickChartServer

Main class for creating and managing candlestick charts.

#### Constructor

```python
CandlestickChartServer(port=5006, title="Candlestick Chart")
```

- `port`: Port number for the web server (default: 5006)
- `title`: Chart title

#### Methods

##### `set_data(bars, pivots=None)`
Set the bar data and optional pivot data for the chart.

- `bars`: List of Bar objects containing OHLCV data
- `pivots`: Optional list of Pivot objects for zigzag overlay

##### `start_server(show_browser=True)`
Start the interactive Bokeh server.

- `show_browser`: Whether to automatically open browser (default: True)
- Returns: URL of the server

##### `stop_server()`
Stop the Bokeh server and clean up resources.

##### `save_static_chart(filename="candlestick_chart.html")`
Save a static HTML version of the chart.

- `filename`: Output filename for the HTML chart
- Returns: Filename of the saved chart

### Convenience Functions

#### `create_chart_from_bars(bars, pivots=None, title="TSLA Candlestick Chart", port=5006)`

Quick setup function that creates a chart server and starts it immediately.

## Chart Features

### Candlestick Visualization
- **Green candles**: Close price higher than open (bullish)
- **Red candles**: Close price lower than open (bearish)
- **Wicks**: Show high and low prices for each period
- **Body height**: Represents the difference between open and close

### Zigzag Pivot Overlay
- **Blue dots**: Zigzag low pivots
- **Orange dots**: Zigzag high pivots  
- **Purple line**: Connects consecutive pivots
- **Configurable threshold**: Set percentage change for pivot detection

### Interactive Tools
- **Pan**: Click and drag to move around the chart
- **Zoom**: Mouse wheel to zoom in/out
- **Box Zoom**: Select area to zoom
- **Reset**: Return to original view
- **Hover**: Detailed OHLCV information on mouseover

## Data Integration

### Bar Data Structure
The system expects Bar objects with the following attributes:
```python
@dataclass
class Bar:
    time: datetime      # Timestamp 
    open: float        # Opening price
    high: float        # Highest price
    low: float         # Lowest price
    close: float       # Closing price
    volume: float      # Trading volume
    idx: int          # Unix timestamp
    props: dict       # Optional properties
```

### Zigzag Pivot Structure
```python
@dataclass
class Pivot:
    price: float      # Pivot price level
    is_low: bool      # True for lows, False for highs
    idx: int         # Unix timestamp
    prop: dict       # Optional properties
```

## Examples

### Multiple Timeframe Analysis
```python
timeframes = [
    (Interval.in_5_minute, "5min", 100),
    (Interval.in_1_hour, "1hour", 50),
    (Interval.in_4_hour, "4hour", 25)
]

for interval, name, n_bars in timeframes:
    bars = GetBarsForSymbol("TSLA", "NASDAQ", interval, n_bars)
    
    chart = CandlestickChartServer(title=f"TSLA {name}")
    chart.set_data(bars)
    chart.save_static_chart(f"tsla_{name}.html")
```

### Custom Styling and Configuration
```python
# Create chart with custom settings
chart = CandlestickChartServer(
    port=8080,
    title="Custom TSLA Analysis"
)

# Set data
chart.set_data(bars, pivots)

# Start server without opening browser
url = chart.start_server(show_browser=False)
print(f"Chart available at: {url}")
```

## Dependencies

- `bokeh`: Interactive visualization library
- `pandas`: Data manipulation
- `numpy`: Numerical computing
- `loguru`: Logging
- `tvdatafeed`: Market data fetching
- `pytz`: Timezone handling

## Installation

Install required packages:
```bash
pip install bokeh pandas numpy loguru tvdatafeed pytz
```

## Browser Compatibility

The charts work in all modern browsers:
- Chrome/Chromium
- Firefox
- Safari
- Edge

## Performance Notes

- For best performance, limit data to 1000-2000 bars per chart
- Static charts load faster than interactive servers
- Use appropriate timeframes for your analysis needs
- Interactive servers automatically clean up when stopped

## Troubleshooting

### Port Already in Use
If you get a port error, either:
1. Change the port number: `CandlestickChartServer(port=5007)`
2. Stop existing servers before starting new ones

### Data Issues
- Ensure Bar objects have valid datetime objects
- Check that price data is numeric (float)
- Verify timezone handling for datetime fields

### Browser Not Opening
- Manually navigate to the displayed URL
- Check firewall settings
- Use `show_browser=False` and open manually
