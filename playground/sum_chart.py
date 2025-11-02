from bar import Bar, GetBarsForSymbol
from loguru import logger
from tvDatafeed import TvDatafeed, Interval
from zigzag import Zigzag


bars_for_tsla = GetBarsForSymbol(
    symbol="TSLA", exchange="NASDAQ", interval=Interval.in_30_minute, n_bars=500
)
logger.info(f"Fetched {len(bars_for_tsla)} bars for TSLA")
logger.info(f"Last bar: {bars_for_tsla[-1]}")

zigzag = Zigzag(pct_change=5)

for bar in bars_for_tsla:
    zigzag.HandleBar(bar)

logger.info(f"Identified {len(zigzag.pivots)} pivots:")
for pivot in zigzag.pivots:
    logger.info(
        f"Pivot at idx {pivot.idx} with price {pivot.price} (is_low={pivot.is_low})"
    )
