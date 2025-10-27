from tvDatafeed import TvDatafeed, Interval

tv = TvDatafeed()
bars = tv.get_hist(
    symbol="TSLA",
    exchange="NASDAQ",
    interval=Interval.in_30_minute,
    n_bars=2000,
    extended_session=False,
)
bars.shape

import pandas as pd

import pytz

# Get PDT timezone
pdt = pytz.timezone("America/Los_Angeles")
bars.index = bars.index.tz_localize(pdt)
bars.index = bars.index.tz_convert("UTC")

# Serialize bars data to CSV file
bars.to_csv("tsla_bars_rth.csv")

# Deserialize (read) bars data from CSV file
bars_loaded = pd.read_csv("tsla_bars_rth.csv", index_col=0, parse_dates=True)
