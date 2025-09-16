import os
import sys
import argparse
import logging
import pathlib
from dotenv import load_dotenv
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy import create_engine, select, insert, update, and_
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
                if args.date:
                    try:
                        d_local = to_date(args.date)
                    except ValueError:
                        LOG.error("Invalid --date, expected YYYY-MM-DD")
                        return 2
                else:
                    d_local = local_yesterday(tz)

                LOG.info("User %s (id=%s, tz=%s) target day=%s", uname, uid, tz, d_local)

                row = conn.execute(
                    select(
                        ReflectionsTable.c.summary, ReflectionsTable.c.highs, ReflectionsTable.c.lows,
                        ReflectionsTable.c.buffalos, ReflectionsTable.c.mood, ReflectionsTable.c.gratitude
                    ).where(and_(
                        ReflectionsTable.c.user_id == uid,
                        ReflectionsTable.c.day_local == d_local
                    ))
                ).mappings().first()

                if not row:
                    LOG.info("  ↳ Skip: no reflection for %s", d_local)
                    continue

                text = build_input_text(row)
                if not text:
                    LOG.info("  ↳ Skip: reflection exists but no content")
                    continue

                try:
                    if args.dry_run:
                        LOG.info("  ↳ [DRY] OpenAI prompt:\n%s\n", text)
                        ai_summary = "(dry-run) positive 20-word summary goes here"
                    else:
                        LOG.debug("  ↳ Calling OpenAI…")
                        ai_summary = call_openai(text)
                    LOG.info("  ↳ Summary: %s", ai_summary)
                except Exception as e:
                    LOG.error("  ↳ OpenAI call failed: %s", e)
                    continue

                try:
                    rid, created = upsert_day_summary(conn, uid, d_local, ai_summary, dry_run=args.dry_run)
                    LOG.info("  ↳ %s ai_processed_reflections id=%s", "Created" if created else "Updated", rid)
                    total_processed += 1
                except SQLAlchemyError as e:
                    LOG.error("  ↳ DB write failed: %s", e)
                    continue

                # inside the per-user loop, AFTER the daily upsert block
                today_local = datetime.now(ZoneInfo(tz)).date()


            # SEPARATE LOOP to do weekly/monthly
            for uid, uname, tzname in users:
                tz = tzname or "UTC"
                if args.date:
                    try:
                        d_local = to_date(args.date)
                    except ValueError:
                        LOG.error("Invalid --date, expected YYYY-MM-DD")
                        return 2
                else:
                    d_local = local_yesterday(tz)

                LOG.info("User %s (id=%s, tz=%s) target day=%s", uname, uid, tz, d_local)

                # -----------------------------------
                # WEEKLY: only on Mondays, or --force-week
                # -----------------------------------
                if args.force_week or today_local.weekday() == 0:
                    wk_start, wk_end = last_week_mon_sun_ending_yesterday(today_local)
                    # collect existing day AI summaries for that Mon..Sun window
                    week_items = collect_day_ai_summaries(conn, uid, wk_start, wk_end)
                    if week_items:
                        week_prompt = build_scope_prompt("week", week_items)
                        if args.dry_run:
                            LOG.info("  ↳ [DRY] Week prompt %s..%s (%d items)", wk_start, wk_end, len(week_items))
                            week_summary = "(dry-run) weekly summary"
                        else:
                            week_summary = call_openai(week_prompt)

                        # target_date for week = end of the window (Sunday)
                        wid, w_created = upsert_scope_summary(conn, uid, wk_end, "week", week_summary, dry_run=args.dry_run)
                        LOG.info("  ↳ %s week rollup id=%s (range %s..%s)", "Created" if w_created else "Updated", wid, wk_start, wk_end)
                    else:
                        LOG.info("  ↳ Skip week rollup: no daily AI summaries in %s..%s", wk_start, wk_end)

                # -----------------------------------
                # MONTHLY: only on the 2nd, or --force-month
                # -----------------------------------
                if args.force_month or today_local.day == 2:
                    mn_start, mn_end = prev_calendar_month_range(today_local)  # full previous month
                    month_items = collect_day_ai_summaries(conn, uid, mn_start, mn_end)
                    if month_items:
                        month_prompt = build_scope_prompt("month", month_items)
                        if args.dry_run:
                            LOG.info("  ↳ [DRY] Month prompt %s..%s (%d items)", mn_start, mn_end, len(month_items))
                            month_summary = "(dry-run) monthly summary"
                        else:
                            month_summary = call_openai(month_prompt)

                        # target_date for month = last day of previous month
                        mid, m_created = upsert_scope_summary(conn, uid, mn_end, "month", month_summary, dry_run=args.dry_run)
                        LOG.info("  ↳ %s month rollup id=%s (range %s..%s)", "Created" if m_created else "Updated", mid, mn_start, mn_end)
                    else:
                        LOG.info("  ↳ Skip month rollup: no daily AI summaries in %s..%s", mn_start, mn_end)


            LOG.info("Done. Processed %d summaries.", total_processed)
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