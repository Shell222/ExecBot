from dataclasses import dataclass
from datetime import datetime
from typing import List

from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import pytz
from loguru import logger


@dataclass
class Bar:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    idx: int
    props: dict = None


class TvClient:
    """
    A client wrapper for TradingView data fetching using tvDatafeed.
    """

    def __init__(self):
        self.tv = TvDatafeed()
        logger.info("TvClient initialized")

    def get_bars(
        self, symbol: str, exchange: str, interval: Interval, n_bars: int = 200
    ) -> List[Bar]:
        """
        Fetch bars for a given symbol and interval.

        Args:
            symbol: Trading symbol (e.g., "TSLA")
            exchange: Exchange name (e.g., "NASDAQ")
            interval: Time interval for bars
            n_bars: Number of bars to fetch

        Returns:
            List of Bar objects
        """
        try:
            raw_bars = self.tv.get_hist(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                n_bars=n_bars,
                extended_session=True,
            )

            logger.info(f"Fetched {len(raw_bars)} bars for {symbol} on {exchange}")

            local_tz = datetime.now().astimezone().tzinfo  # Use system's local timezone
            raw_bars.index = raw_bars.index.tz_localize(local_tz)
            raw_bars.index = raw_bars.index.tz_convert("UTC")

            bars = []
            for idx, row in raw_bars.iterrows():
                bar = Bar(
                    time=idx,
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                    idx=int(idx.timestamp()),
                )
                bars.append(bar)
            return bars
        except Exception as e:
            logger.error(f"Error fetching bars for {symbol}: {e}")
            return []


def GetBarsForSymbol(symbol: str, exchange: str, interval: Interval, n_bars: int):
    """
    Legacy function for backward compatibility.
    Consider using TvClient.get_bars() directly for new code.
    """
    tv_client = TvClient()
    return tv_client.get_bars(symbol, exchange, interval, n_bars)


bars_for_tsla = GetBarsForSymbol(
    symbol="TSLA", exchange="NASDAQ", interval=Interval.in_30_minute, n_bars=500
)
logger.info(f"Fetched {len(bars_for_tsla)} bars for TSLA")
logger.info(f"Last bar: {bars_for_tsla[-1]}")
