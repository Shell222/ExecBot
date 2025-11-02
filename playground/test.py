import time
import pytz


est = pytz.timezone("America/New_York")
system_timezone = time.tzname[0]
print(f"System timezone: {time.tzname}")
