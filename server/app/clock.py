from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Seoul")


def today() -> date:
    return datetime.now(TZ).date()
