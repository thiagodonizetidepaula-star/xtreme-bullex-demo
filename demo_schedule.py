"""Fixed Brazil-local DEMO windows. No broker order, real-account or credential logic."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('America/Sao_Paulo')
SLOTS = ('10:00', '14:00', '20:00')
WINDOW_SECONDS = 10 * 60


def local_day(timestamp):
    return datetime.fromtimestamp(timestamp, ZONE).strftime('%Y-%m-%d')


def slot_times(timestamp, slot, warmup_seconds=300):
    """Return UTC epoch seconds for today's warmup/start/deadline in São Paulo."""
    if slot not in SLOTS:
        raise ValueError('Horário fora da agenda DEMO.')
    local = datetime.fromtimestamp(timestamp, ZONE)
    hour, minute = map(int, slot.split(':'))
    start = local.replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()
    return start-warmup_seconds, start, start+WINDOW_SECONDS


def warmup_seconds(timeframe):
    """Allow 42 closed bars where practical; never exceed the 60m auto limit."""
    return max(300, min(3000, int(timeframe)*45))


def next_unspent_slot(timestamp, spent):
    """Next eligible slot, never silently backfill a missed past window."""
    local = datetime.fromtimestamp(timestamp, ZONE)
    for days in (0, 1):
        day = (local+timedelta(days=days)).strftime('%Y-%m-%d')
        for slot in SLOTS:
            hour, minute = map(int, slot.split(':'))
            start = (local+timedelta(days=days)).replace(
                hour=hour,minute=minute,second=0,microsecond=0).timestamp()
            if (day, slot) not in spent and timestamp < start+WINDOW_SECONDS:
                return {'day':day,'slot':slot,'start':start,'deadline':start+WINDOW_SECONDS}
    return None
