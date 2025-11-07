from Server.constants import CHALLENGE_MULT, IMPORTANCE_MULT
from datetime import datetime, date, timedelta, timezone, time
from zoneinfo import ZoneInfo

# GUIDING RULE: 1 task = 10% of a goal = 30 minutes of work = 100 points = $1
def compute_points(points_mode, base_value, challenge, importance, time_minutes=None, percent_value=None, is_focused=False):
    base = float(base_value or 1.0)
    c = CHALLENGE_MULT[challenge]
    i = IMPORTANCE_MULT[int(importance)]
    if points_mode == "tasks":
        payload = 100.0 # 1 task = 100
    elif points_mode == "time":
        payload = 100.0 * (max(0, (time_minutes or 0)) / 30.0) # 30 mins = 100
    else:  # percent
        payload = 10.0 * max(0.0, min(100.0, float(percent_value or 0))) # 10% = 100
    if is_focused:
        payload = round(payload * 2.0, 2)
    return round(base * c * i * payload, 2)


def potential_points_for_habit(points_mode, base_value, challenge, importance, time_target=None, percent_target=None, is_focused=False):
    if points_mode == "tasks":
        return compute_points("tasks", base_value, challenge, importance, None, None, is_focused=is_focused)
    if points_mode == "time":
        return compute_points("time", base_value, challenge, importance, time_minutes=time_target or 0, is_focused=is_focused) 
    return compute_points("percent", base_value, challenge, importance, percent_value=percent_target or 0, is_focused=is_focused)

def parse_local_day(s: str) -> date:
    y, m, d = map(int, s.split("-"))
    return date(y, m, d)

def start_of_week(d: date) -> date:
    # Sunday-start week: weekday(): Mon=0..Sun=6 -> shift so Sun=0
    # If you prefer Monday-start, use: d - timedelta(days=(d.weekday()))
    return d - timedelta(days=(d.weekday() + 1) % 7)

def end_of_week(d: date) -> date:
    s = start_of_week(d)
    return s + timedelta(days=6)

def month_bounds(d: date) -> tuple[date, date]:
    first = d.replace(day=1)
    if first.month == 12:
        next_first = first.replace(year=first.year+1, month=1)
    else:
        next_first = first.replace(month=first.month+1)
    last = next_first - timedelta(days=1)
    return first, last

def week_bounds(d: date, week_start: int = 0) -> tuple[date, date]:
    """
    Return (start, end) dates for the week containing `d`, inclusive.

    Args:
        d: a date (local calendar day)
        week_start: 0=Monday .. 6=Sunday. Default 0 (ISO weeks Mon-Sun).

    Example:
        >>> week_bounds(date(2025, 9, 14))  # 2025-09-14 is a Sunday
        (date(2025, 9, 8), date(2025, 9, 14))  # Mon..Sun
    """
    if not isinstance(d, date):
        raise TypeError("week_bounds expects a datetime.date")

    # Python's date.weekday(): Monday=0..Sunday=6
    delta = (d.weekday() - week_start) % 7
    start = d - timedelta(days=delta)
    end = start + timedelta(days=6)
    return start, end

def date_range_inclusive(a: date, b: date):
    cur = a
    while cur <= b:
        yield cur
        cur += timedelta(days=1)

def local_midnight_to_utc(dt_local_day: date, tz: str) -> datetime:
    z = ZoneInfo(tz)
    return datetime(dt_local_day.year, dt_local_day.month, dt_local_day.day, 0, 0, 0, tzinfo=z).astimezone(ZoneInfo("UTC"))

def _day_start_utc(day_local: date, tzname: str):
    """
    Convert a local day (YYYY-MM-DD) to the **UTC-start-of-that-day**
    as a naive datetime (UTC-equivalent) to match your DB convention.

    Example:
      day_local='2025-10-29' in 'America/Los_Angeles' (UTC-7)
      → 2025-10-29T00:00:00-07:00 local
      → 2025-10-29T07:00:00Z UTC
      → returns naive: datetime(2025,10,29,7,0,0)
    """
    # midnight LOCAL timezone → aware datetime
    local_dt = datetime.combine(day_local, time(0,0), ZoneInfo(tzname))
    # convert to UTC, then drop tzinfo to match your DB fields
    return local_dt.astimezone(timezone.utc).replace(tzinfo=None)

def sunday0_dow(day_local):
    """Map Python Mon=0..Sun=6 to your Sunday=0..Saturday=6 scheme."""
    return (day_local.weekday() + 1) % 7  # Sun=0 .. Sat=6

def habit_active_on_day(rec, day_local, tzname):
    """
    - Recurring habits are available on days listed in `schedule` (JSON array of ints Sun=0..Sat=6).
    - If schedule is NULL/empty → available every day.
    - Must also respect created_at_utc (habit first appears the day it was created).
    """
    # one-offs handled elsewhere
    if rec["type"] != "recurring":
        return False

    # Respect creation time: habit is valid on the exact day it's created.
    day_start_utc = _day_start_utc(day_local, tzname)
    day_end_utc   = day_start_utc + timedelta(days=1)

    created_at = rec.get("created_at_utc")
    if created_at is not None:
        # STRICTLY skip only if created AFTER the day ends.
        # This includes the whole local day on which it was created.
        if created_at > day_end_utc:
            return False

    # Schedule check
    sched = rec.get("schedule") or []  # JSON column deserializes to list or None
    if len(sched) == 0:
        return True  # empty/null means every day

    todays_dow = sunday0_dow(day_local)
    return todays_dow in sched

def _normalize_schedule(v):
    if v is None:
        return None
    if not isinstance(v, list):
        raise ValueError("schedule must be a list of integers 0..6 (Sun=0..Sat=6)")
    try:
        vals = sorted({int(x) for x in v})
    except Exception:
        raise ValueError("schedule must be integers 0..6")
    if any(x < 0 or x > 6 for x in vals):
        raise ValueError("schedule values must be 0..6 (Sun=0..Sat=6)")
    return vals
