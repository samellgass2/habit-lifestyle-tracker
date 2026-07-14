import os, pathlib
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
from sqlalchemy import create_engine, select, insert
from Server.models import UsersTable, AiGeneratedMotivationsTable, metadata
from Server.ai_utils import generate_motivation, OPENAI_MODEL, PROMPT_VERSION, adam_round_start, adam_round_finish

LOG = logging.getLogger("motivation_daily")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "Server" / ".env")
DB_CNF = os.getenv("MYSQL_CNF")

def main():
    if not DB_CNF:
        LOG.error("MYSQL_CNF not set")
        return 2

    engine = create_engine(
        "mysql+pymysql://",
        connect_args={"read_default_file": DB_CNF, "read_default_group": "client"},
        pool_pre_ping=True, future=True
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with engine.begin() as conn:
        users = conn.execute(select(UsersTable.c.id)).all()
        # L3 batch round (INV-RC-8): per-user motivations roll up to ONE entry.
        adam_round_start("daily-motivation")
        n = 0
        for (uid,) in users:
            try:
                text = generate_motivation(conn, uid)
                conn.execute(
                    insert(AiGeneratedMotivationsTable).values(
                        user_id=uid, text=text, source="daily",
                        model=OPENAI_MODEL, prompt_version=PROMPT_VERSION,
                        generated_at_utc=now
                    )
                )
                n += 1
                LOG.info("Generated daily motivation for user %s", uid)
            except Exception as e:
                LOG.warning("User %s failed: %s", uid, e)
        adam_round_finish(summary=f"daily motivation for {n} user(s)")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
