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
    return p.parse_args()

def local_yesterday(tzname: str):
    today = datetime.now(ZoneInfo(tzname)).date()
    return today - timedelta(days=1)

def to_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def build_input_text(ref):
    parts = []
    if ref.get("summary"):  parts.append(f"Summary: {ref['summary']}")
    if ref.get("highs"): parts.append(f"High points: {ref['highs']}")
    if ref.get("highs"): parts.append(f"Low points: {ref['lows']}")
    if ref.get("buffalos"): parts.append(f"Weird/funny moments: {ref['buffalos']}")
    if ref.get("mood") is not None:
        parts.append(f"Mood: {ref['mood']}/5")
    return "\n".join(parts).strip()

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
    
def summarize_for_all_users():
    with engine.begin() as conn:
        users = conn.execute(select(UsersTable.c.id, UsersTable.c.timezone)).all()
        for uid, tzname in users:
            tz = tzname or "UTC"
            day = local_yesterday(tz)

            # fetch that day's reflection
            row = conn.execute(
                select(
                    ReflectionsTable.c.summary, ReflectionsTable.c.mood, 
                    ReflectionsTable.c.highs, ReflectionsTable.c.lows,
                    ReflectionsTable.c.buffalos
                ).where(and_(
                    ReflectionsTable.c.user_id == uid,
                    ReflectionsTable.c.day_local == day
                ))
            ).mappings().first()

            if not row:
                # nothing to summarize; skip
                continue

            text = build_input_text(row)
            if not text:
                continue

            try:
                ai = call_openai(text)
            except Exception as e:
                # log and continue with next user
                print(f"[WARN] OpenAI failed for user {uid} {day}: {e}")
                continue

            rid, created = upsert_day_summary(conn, uid, day, ai)
            print(f"[OK] {'created' if created else 'updated'} AI summary for user {uid} {day} (id {rid})")

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