# Processes/focus_picker.py (patterned after your summarizer)
import random
import pathlib
import os
from dotenv import load_dotenv
import argparse
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from sqlalchemy import select, func, and_, update, create_engine
from Server.models import UsersTable, CategoriesTable, CompletedHabitsTable
from Server.ai_utils import get_client  # reuse your OpenAI client
import logging

ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "Server" / ".env")

LOG = logging.getLogger("focus_picker")

def setup_logging(verbosity: int):
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    # Nuke any pre-existing handlers and apply our format
    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    # quiet some noisy libs unless -vv
    clamp = logging.DEBUG if level == logging.DEBUG else logging.WARNING
    for name in ["sqlalchemy", "urllib3", "httpx", "openai"]:
        logging.getLogger(name).setLevel(clamp)

def parse_args():
    p = argparse.ArgumentParser(description="Pick weekly focus category and write AI blurb")
    p.add_argument("-v", "--verbose", action="count", default=0, help="increase verbosity (-v|-vv)")
    p.add_argument("--dry-run", action="store_true", help="compute but do not write DB updates")
    return p.parse_args()

def last_week_mon_sun(today: date):
    """
    Return the Monday..Sunday for the most recent fully concluded week.
    If today is Wed 2025-10-29, this returns Mon 2025-10-20 .. Sun 2025-10-26.
    """
    # Monday=0..Sunday=6
    weekday = today.weekday()
    # Go back to last Monday of the previous week (i.e., 7 + weekday days)
    last_monday = today - timedelta(days=weekday + 7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday, last_sunday

def build_focus_blurb_prompt(username: str, cat_name: str, sample_accomplishments: list[str]):
    sys = "You are a supportive coach. Write a 2–3 sentence upbeat blurb about why focusing this category this week will be energizing. Keep it specific but short."
    bullets = "\n".join(f"- {s}" for s in sample_accomplishments[:5])
    usr = (
        f"User: {username}\n"
        f"Category: {cat_name}\n"
        f"Recent accomplishments:\n{bullets if bullets else '- (no recent items)'}\n"
        "Write 20–40 words. Avoid platitudes and keep it concrete."
    )
    return [{"role":"system","content":sys},{"role":"user","content":usr}]

def pick_weighted(items):
    # items: [(cat_id, points_sum)]
    weights = [1.0 / (p + 1.0) for _, p in items]
    total = sum(weights) or 1.0
    r = random.random() * total
    acc = 0.0
    for (cid, _), w in zip(items, weights):
        acc += w
        if r <= acc:
            return cid
    return items[-1][0]  # fallback


def run(engine):
    LOG.info("=== Weekly Focus Selection Started ===")

    with engine.begin() as c:
        users = c.execute(select(
            UsersTable.c.id,
            UsersTable.c.username,
            UsersTable.c.timezone
        )).all()

    cli = get_client()

    for uid, uname, tzname in users:
        tz = tzname or "UTC"
        today = datetime.now(ZoneInfo(tz)).date()
        wk_start, wk_end = last_week_mon_sun(today)

        LOG.info(f"[User {uid} | @{uname}] tz={tz} week={wk_start}→{wk_end}")

        with engine.begin() as c:
            cats = c.execute(select(
                CategoriesTable.c.id,
                CategoriesTable.c.category_name
            ).where(CategoriesTable.c.user_id == uid)).all()

            if not cats:
                LOG.warning(f"[User {uid}] Has no categories — skipping.")
                continue

            pts = c.execute(
                select(
                    CompletedHabitsTable.c.category_id,
                    func.coalesce(func.sum(CompletedHabitsTable.c.points_awarded), 0.0)
                )
                .where(and_(
                    CompletedHabitsTable.c.user_id == uid,
                    CompletedHabitsTable.c.day_local >= wk_start,
                    CompletedHabitsTable.c.day_local <= wk_end,
                ))
                .group_by(CompletedHabitsTable.c.category_id)
            ).all()
            points_by_cat = {cid: float(p or 0.0) for cid, p in pts}

        # log stats
        LOG.info(f"[User {uid}] Category points last week:")
        for cid, cname in cats:
            LOG.info(f"    {cname:<15}: {points_by_cat.get(cid, 0.0)} pts")

        ranked = [(cid, points_by_cat.get(cid, 0.0)) for cid, _ in cats]
        weights = [1.0 / (p + 1.0) for _, p in ranked]
        total_w = sum(weights) or 1.0

        LOG.info(f"[User {uid}] Weights:")
        for (cid, cname), w, (_, p) in zip(cats, weights, ranked):
            LOG.info(f"    {cname:<15}: weight={w:.3f} (points={p})")

        focus_cid = pick_weighted(ranked)
        focus_name = next(n for cid, n in cats if cid == focus_cid)

        LOG.info(f"[User {uid}] PICKED: {focus_name} ✅")

        # Get examples for blurb generation
        with engine.begin() as c:
            examples = c.execute(
                select(CompletedHabitsTable.c.name_snapshot)
                .where(and_(
                    CompletedHabitsTable.c.user_id == uid,
                    CompletedHabitsTable.c.category_id == focus_cid,
                    CompletedHabitsTable.c.day_local >= wk_start - timedelta(days=21),
                    CompletedHabitsTable.c.day_local <= wk_end,
                ))
                .order_by(CompletedHabitsTable.c.completed_at_local.desc())
                .limit(8)
            ).scalars().all()

        msgs = build_focus_blurb_prompt(uname, focus_name, examples)
        resp = cli.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.7,
            messages=msgs
        )
        blurb = resp.choices[0].message.content.strip()

        LOG.info(f"[User {uid}] AI Blurb:\n---\n{blurb}\n---")

        # Flip focus in DB
        if os.getenv("FOCUS_PICKER_DRY_RUN") == "1":
            LOG.info(f"[User {uid}] (dry-run) Would set '{focus_name}' focused=True and write AI blurb")
        else:
            now_utc = datetime.utcnow()
            with engine.begin() as c:
                c.execute(update(CategoriesTable)
                        .where(and_(CategoriesTable.c.user_id == uid,
                                    CategoriesTable.c.is_focused == True))
                        .values(is_focused=False, ai_summary=None))

                c.execute(update(CategoriesTable)
                        .where(and_(CategoriesTable.c.user_id == uid,
                                    CategoriesTable.c.id == focus_cid))
                        .values(is_focused=True,
                                ai_summary=blurb,
                                updated_at_utc=now_utc))

            LOG.info(f"[User {uid}] ✅ Updated DB — {focus_name} now in focus")

    LOG.info("=== Weekly Focus Selection Completed ===")

def main():
    args = parse_args()
    setup_logging(args.verbose)
    LOG.info("focus_picker starting (dry_run=%s)", args.dry_run)

    # Build engine like your other processes do
    db_cnf = os.getenv("MYSQL_CNF") 
    if not db_cnf:
        LOG.error("MYSQL_CNF not set; export MYSQL_CNF pointing to your my.cnf with [client] creds")
        return 2

    engine = create_engine(
        "mysql+pymysql://",
        connect_args={"read_default_file": db_cnf, "read_default_group": "client"},
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
    )

    if args.dry_run:
        # Wrap run() so we don’t commit updates—easy way: monkeypatch engine.begin()
        # but since your run() uses engine.begin() for both reads/writes,
        # we can simply run and skip the final write block by guarding inside run().
        # Quick option: set an env and check it inside run().
        os.environ["FOCUS_PICKER_DRY_RUN"] = "1"

    try:
        run(engine)
        LOG.info("focus_picker done")
        return 0
    except Exception as e:
        LOG.exception("focus_picker failed: %s", e)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())