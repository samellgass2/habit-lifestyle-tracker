import os
import sys
import argparse
import logging
import pathlib
from dotenv import load_dotenv
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy import create_engine, select, insert, update, and_, func
from sqlalchemy.exc import SQLAlchemyError

# import your shared models

from Server.models import UsersTable, ReflectionsTable, AiProcessedReflectionsTable, metadata

# ----- Logging ---------------------------------------------------------------
LOG = logging.getLogger("summarizer")

def setup_logging(verbosity: int):
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

# ----- ENV -------------------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parents[1]  # project root
LOG.info("Loading env from {}".format(ROOT))
load_dotenv(ROOT / "Server" / ".env")
DB_CNF = os.getenv("MYSQL_CNF")  # cnf filepath
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
PROMPT_VERSION = "v1"


# --- OpenAI client ---
from openai import OpenAI
client = None
def get_client():
    global client
    if client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY missing")
        client = OpenAI(api_key=OPENAI_API_KEY)
    return client


def parse_args():
    p = argparse.ArgumentParser(description="Summarize daily reflections with OpenAI.")
    p.add_argument("--date", help="Target local date (YYYY-MM-DD). Default: yesterday in user's TZ.")
    p.add_argument("--user-id", type=int, help="Only process this user id.")
    p.add_argument("--user", help="Only process this username.")
    p.add_argument("--dry-run", action="store_true", help="Don't write to DB.")
    p.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity (-v, -vv).")
    p.add_argument("--force-week", action="store_true", help="Force weekly rollup regardless of weekday.")
    p.add_argument("--force-month", action="store_true", help="Force monthly rollup regardless of day of month.")

    return p.parse_args()

def local_yesterday(tzname: str):
    today = datetime.now(ZoneInfo(tzname)).date()
    return today - timedelta(days=1)

def to_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def build_input_text(ref):
    parts = []
    if ref.get("summary"):  parts.append(f"Summary: {ref['summary']}")
    if ref.get("highs"):    parts.append(f"High points: {ref['highs']}")
    if ref.get("lows"):     parts.append(f"Low points: {ref['lows']}")  # <- fixed
    if ref.get("buffalos"): parts.append(f"Weird/funny moments: {ref['buffalos']}")
    if ref.get("mood") is not None:
        parts.append(f"Mood: {ref['mood']}/5")
    return "\n".join(parts).strip()

def upsert_scope_summary(conn, user_id: int, end_day_local: date, scope: str, summary_text: str, dry_run=False):
    """
    scope: 'week' or 'month' (rolling windows ending end_day_local)
    """
    now_utc = datetime.utcnow()
    existing_id = conn.execute(
        select(AiProcessedReflectionsTable.c.id).where(and_(
            AiProcessedReflectionsTable.c.user_id == user_id,
            AiProcessedReflectionsTable.c.scope == scope,
            AiProcessedReflectionsTable.c.kind == "summary",
            AiProcessedReflectionsTable.c.target_date == end_day_local,
        ))
    ).scalar()

    values = dict(
        summary=summary_text,
        model=OPENAI_MODEL,
        prompt_version=PROMPT_VERSION,
        generated_at_utc=now_utc,
    )

    if dry_run:
        LOG.info("[DRY] Would %s %s summary for user=%s end=%s",
                 "update" if existing_id else "insert", scope, user_id, end_day_local)
        return existing_id or -1, not bool(existing_id)

    if existing_id:
        conn.execute(
            update(AiProcessedReflectionsTable)
            .where(AiProcessedReflectionsTable.c.id == existing_id)
            .values(**values)
        )
        return existing_id, False
    else:
        res = conn.execute(
            insert(AiProcessedReflectionsTable).values(
                user_id=user_id, scope=scope, kind="summary",
                target_date=end_day_local, **values
            )
        )
        return res.inserted_primary_key[0], True

def collect_day_ai_summaries(conn, user_id: int, start_day: date, end_day: date):
    """
    Returns a list of dicts [{day: date, summary: str}], ordered by day.
    """
    rows = conn.execute(
        select(
            AiProcessedReflectionsTable.c.target_date,
            AiProcessedReflectionsTable.c.summary
        ).where(and_(
            AiProcessedReflectionsTable.c.user_id == user_id,
            AiProcessedReflectionsTable.c.scope == "day",
            AiProcessedReflectionsTable.c.kind == "summary",
            AiProcessedReflectionsTable.c.target_date >= start_day,
            AiProcessedReflectionsTable.c.target_date <= end_day,
        )).order_by(AiProcessedReflectionsTable.c.target_date.asc())
    ).all()

    out = []
    for d, s in rows:
        if s and s.strip():
            out.append({"day": d, "summary": s.strip()})
    return out


def build_scope_prompt(scope: str, items: list[dict]):
    """
    scope: 'week' | 'month'
    items: [{day: date, summary: str}]
    """
    header = f"Summarize the following {scope} of daily highlights into a concise, positive synthesis.\n" \
             f"Lean motivational, second-person, weave notable highs/lows/buffalos and trend in mood, 100–130 words.\n"
    bullet_lines = []
    for it in items:
        bullet_lines.append(f"- {it['day']}: {it['summary']}")
    return header + "\n".join(bullet_lines)

def prev_calendar_month_range(today: date):
    """Return (start, end) for the previous calendar month based on 'today'."""
    first_this_month = date(today.year, today.month, 1)
    last_prev = first_this_month - timedelta(days=1)
    first_prev = date(last_prev.year, last_prev.month, 1)
    return first_prev, last_prev

def last_week_mon_sun_ending_yesterday(today: date):
    """
    If today is Monday, yesterday is Sunday. Return (mon, sun) of the *immediately previous* week.
    Works even if forced on a non-Mon day (we still summarize the 7 days ending yesterday).
    """
    end = today - timedelta(days=1)  # yesterday (typically Sunday on Mondays)
    start = end - timedelta(days=6)  # 7-day window Mon..Sun
    return start, end

def latest_reflection_day(conn, user_id: int) -> date | None:
    """Return the most recent day_local that has any reflection content."""
    return conn.execute(
        select(func.max(ReflectionsTable.c.day_local))
        .where(ReflectionsTable.c.user_id == user_id)
    ).scalar()

def concluded_week_range(today_local: date):
    """
    Return (mon, sun) of the most recent fully concluded Mon..Sun week
    relative to 'today_local'. The week must end strictly before today.
    """
    # End = last Sunday strictly before today
    # weekday(): Mon=0..Sun=6
    days_since_sunday = (today_local.weekday() - 6) % 7
    last_sunday = today_local - timedelta(days=days_since_sunday or 7)
    start_monday = last_sunday - timedelta(days=6)
    return start_monday, last_sunday

def reflections_by_day(conn, user_id: int, start_day: date, end_day: date) -> set[date]:
    rows = conn.execute(
        select(ReflectionsTable.c.day_local)
        .where(and_(
            ReflectionsTable.c.user_id == user_id,
            ReflectionsTable.c.day_local >= start_day,
            ReflectionsTable.c.day_local <= end_day,
        ))
        .distinct()
    ).scalars().all()
    return set(rows)

def existing_day_summaries(conn, user_id: int, start_day: date, end_day: date) -> set[date]:
    rows = conn.execute(
        select(AiProcessedReflectionsTable.c.target_date)
        .where(and_(
            AiProcessedReflectionsTable.c.user_id == user_id,
            AiProcessedReflectionsTable.c.scope == "day",
            AiProcessedReflectionsTable.c.kind == "summary",
            AiProcessedReflectionsTable.c.target_date >= start_day,
            AiProcessedReflectionsTable.c.target_date <= end_day,
            AiProcessedReflectionsTable.c.summary.isnot(None),
        ))
    ).scalars().all()
    return set(rows)

def ensure_day_summary(conn, user_id: int, day_local: date, dry_run=False) -> bool:
    """
    Ensure there is a 'day' AI summary for 'day_local' if a reflection exists with content.
    Returns True if a summary was created or updated; False if skipped/no data.
    """
    # fetch reflection row
    row = conn.execute(
        select(
            ReflectionsTable.c.summary, ReflectionsTable.c.highs, ReflectionsTable.c.lows,
            ReflectionsTable.c.buffalos, ReflectionsTable.c.mood, ReflectionsTable.c.gratitude
        ).where(and_(
            ReflectionsTable.c.user_id == user_id,
            ReflectionsTable.c.day_local == day_local
        ))
    ).mappings().first()

    if not row:
        LOG.info("  ↳ Skip day %s: no reflection", day_local)
        return False

    text = build_input_text(row)
    if not text:
        LOG.info("  ↳ Skip day %s: reflection exists but empty", day_local)
        return False

    if dry_run:
        LOG.info("  ↳ [DRY] OpenAI prompt for %s:\n%s\n", day_local, text)
        ai_summary = "(dry-run) positive 30-word summary"
    else:
        ai_summary = call_openai(text)

    rid, created = upsert_day_summary(conn, user_id, day_local, ai_summary, dry_run=dry_run)
    LOG.info("  ↳ %s ai_processed_reflections id=%s for day=%s", "Created" if created else "Updated", rid, day_local)
    return True


SYSTEM_PROMPT = (
  "You will motivate users and focus on the positive outcomes and moments of their days. "
  "Summarize the following into a 30 word overview that highlights positive and noteworthy outcomes and incorporates their highs, "
  "perhaps their lows and also their weird/funny moments, and their mood rating (1 is overwhelmed "
  "and upset, up to 5 is joyful and fulfilled. Your response will be in the 2nd person (you/your pronouns)."
)

@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
)
def call_openai(text: str) -> str:
    cli = get_client()
    resp = cli.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.7,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": text},
        ],
    )
    return resp.choices[0].message.content.strip()

def upsert_day_summary(conn, user_id: int, day_local: date, summary_text: str, dry_run=False):
    now_utc = datetime.utcnow()
    existing_id = conn.execute(
        select(AiProcessedReflectionsTable.c.id).where(and_(
            AiProcessedReflectionsTable.c.user_id == user_id,
            AiProcessedReflectionsTable.c.scope == "day",
            AiProcessedReflectionsTable.c.kind == "summary",
            AiProcessedReflectionsTable.c.target_date == day_local,
        ))
    ).scalar()
    values = dict(
        summary=summary_text,
        model=OPENAI_MODEL,
        prompt_version=PROMPT_VERSION,
        generated_at_utc=now_utc,
    )
    if dry_run:
        LOG.info("[DRY] Would %s AI summary for user=%s day=%s",
                 "update" if existing_id else "insert", user_id, day_local)
        return existing_id or -1, not bool(existing_id)

    if existing_id:
        conn.execute(
            update(AiProcessedReflectionsTable)
            .where(AiProcessedReflectionsTable.c.id == existing_id)
            .values(**values)
        )
        return existing_id, False
    else:
        res = conn.execute(
            insert(AiProcessedReflectionsTable).values(
                user_id=user_id, scope="day", kind="summary",
                target_date=day_local, **values
            )
        )
        return res.inserted_primary_key[0], True

def main():
    args = parse_args()
    setup_logging(args.verbose)

    if not DB_CNF:
        LOG.error("DB_URL missing (set in environment or .env)")
        return 2

    engine = create_engine(
            "mysql+pymysql://",
            connect_args={"read_default_file": DB_CNF, "read_default_group": "client"},
            pool_pre_ping=True, pool_recycle=1800, future=True
        )
    LOG.debug("Connecting to DB: %s", DB_CNF)

    try:
        with engine.begin() as conn:
            # Users filter
            sel = select(UsersTable.c.id, UsersTable.c.username, UsersTable.c.timezone)
            if args.user_id:
                sel = sel.where(UsersTable.c.id == args.user_id)
            if args.user:
                sel = sel.where(UsersTable.c.username == args.user)
            users = conn.execute(sel).all()
            if not users:
                LOG.warning("No users matched filter.")
                return 0

            total_processed = 0

            for uid, uname, tzname in users:
                tz = tzname or "UTC"
                today_local = datetime.now(ZoneInfo(tz)).date()
                LOG.info("User %s (id=%s, tz=%s) today=%s", uname, uid, tz, today_local)

                # ---------------------------
                # 1) DAILY: ensure summary for the latest reflection date
                # ---------------------------
                if args.date:
                    # If the operator pins a date, respect it for daily ensure
                    try:
                        target_day = to_date(args.date)
                    except ValueError:
                        LOG.error("Invalid --date, expected YYYY-MM-DD")
                        return 2
                else:
                    target_day = latest_reflection_day(conn, uid)

                if target_day:
                    if ensure_day_summary(conn, uid, target_day, dry_run=args.dry_run):
                        total_processed += 1
                else:
                    LOG.info("  ↳ Skip daily: no reflections exist yet for this user.")

                # ---------------------------
                # 2) WEEKLY: most recent concluded Mon..Sun before today
                #    Generate iff: no existing week summary for that Sunday AND there is data in range.
                # ---------------------------
                wk_start, wk_end = concluded_week_range(today_local)

                # Is there already a week summary targeting wk_end?
                existing_week_id = conn.execute(
                    select(AiProcessedReflectionsTable.c.id).where(and_(
                        AiProcessedReflectionsTable.c.user_id == uid,
                        AiProcessedReflectionsTable.c.scope == "week",
                        AiProcessedReflectionsTable.c.kind == "summary",
                        AiProcessedReflectionsTable.c.target_date == wk_end,
                    ))
                ).scalar()

                if not existing_week_id or args.force_week:
                    # backfill missing day summaries inside the week for any days that have reflections
                    days_with_refs = reflections_by_day(conn, uid, wk_start, wk_end)
                    if not days_with_refs:
                        LOG.info("  ↳ Skip week %s..%s: no reflections in range.", wk_start, wk_end)
                    else:
                        days_with_day_summ = existing_day_summaries(conn, uid, wk_start, wk_end)
                        missing_days = sorted(days_with_refs - days_with_day_summ)
                        for d in missing_days:
                            ensure_day_summary(conn, uid, d, dry_run=args.dry_run)

                        week_items = collect_day_ai_summaries(conn, uid, wk_start, wk_end)
                        if week_items:
                            week_prompt = build_scope_prompt("week", week_items)
                            if args.dry_run:
                                LOG.info("  ↳ [DRY] Week prompt %s..%s (%d items)", wk_start, wk_end, len(week_items))
                                week_summary = "(dry-run) weekly summary"
                            else:
                                week_summary = call_openai(week_prompt)

                            wid, w_created = upsert_scope_summary(conn, uid, wk_end, "week", week_summary, dry_run=args.dry_run)
                            LOG.info("  ↳ %s week rollup id=%s (range %s..%s)", "Created" if w_created else "Updated", wid, wk_start, wk_end)
                        else:
                            LOG.info("  ↳ Skip week %s..%s: no daily AI summaries after backfill.", wk_start, wk_end)
                else:
                    LOG.info("  ↳ Week %s..%s already summarized (target=%s).", wk_start, wk_end, wk_end)

                # ---------------------------
                # 3) MONTHLY: previous calendar month (fully concluded)
                #    Generate iff: no existing monthly summary for mn_end AND there is data in range.
                # ---------------------------
                mn_start, mn_end = prev_calendar_month_range(today_local)

                existing_month_id = conn.execute(
                    select(AiProcessedReflectionsTable.c.id).where(and_(
                        AiProcessedReflectionsTable.c.user_id == uid,
                        AiProcessedReflectionsTable.c.scope == "month",
                        AiProcessedReflectionsTable.c.kind == "summary",
                        AiProcessedReflectionsTable.c.target_date == mn_end,
                    ))
                ).scalar()

                if not existing_month_id or args.force_month:
                    days_with_refs = reflections_by_day(conn, uid, mn_start, mn_end)
                    if not days_with_refs:
                        LOG.info("  ↳ Skip month %s..%s: no reflections in range.", mn_start, mn_end)
                    else:
                        days_with_day_summ = existing_day_summaries(conn, uid, mn_start, mn_end)
                        missing_days = sorted(days_with_refs - days_with_day_summ)
                        for d in missing_days:
                            ensure_day_summary(conn, uid, d, dry_run=args.dry_run)

                        month_items = collect_day_ai_summaries(conn, uid, mn_start, mn_end)
                        if month_items:
                            month_prompt = build_scope_prompt("month", month_items)
                            if args.dry_run:
                                LOG.info("  ↳ [DRY] Month prompt %s..%s (%d items)", mn_start, mn_end, len(month_items))
                                month_summary = "(dry-run) monthly summary"
                            else:
                                month_summary = call_openai(month_prompt)

                            mid, m_created = upsert_scope_summary(conn, uid, mn_end, "month", month_summary, dry_run=args.dry_run)
                            LOG.info("  ↳ %s month rollup id=%s (range %s..%s)", "Created" if m_created else "Updated", mid, mn_start, mn_end)
                        else:
                            LOG.info("  ↳ Skip month %s..%s: no daily AI summaries after backfill.", mn_start, mn_end)
                else:
                    LOG.info("  ↳ Month %s..%s already summarized (target=%s).", mn_start, mn_end, mn_end)

            LOG.info("Done.")
            return 0

    except Exception as e:
        LOG.exception("Fatal error: %s", e)
        return 1

if __name__ == "__main__":
    sys.exit(main())


# 1. Check date, determine if we will run ONE DAY, (+) SEVEN DAY, (+) 30 DAY summary
    # How often to do the 'year' summary ? Maybe update it monthly as we go ? 

# 2. Authenticate to DB and retrieve appropriate records

# 3. Find openAI auth token (ENVIRONMENT VARIABLE - FIND AND SET)

# 4. Make API call, retry logic if necessary

# 5. Write summmarized records to appropriate table