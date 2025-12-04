import os, secrets, hashlib
from datetime import datetime, timedelta, timezone, date
from collections import Counter, defaultdict
from calendar import monthrange
from flask import Flask, jsonify, request, g, make_response, Blueprint
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, select, delete, insert, func, update, and_, or_, literal
from sqlalchemy.exc import SQLAlchemyError
from zoneinfo import ZoneInfo
from werkzeug.security import generate_password_hash, check_password_hash


from Server.models import (
    UsersTable,
    FriendsTable,
    SessionsTable,
    ReflectionsTable,
    AiProcessedReflectionsTable,
    create_all_tables,
    CategoriesTable,
    HabitsTable,
    PendingHabitsTable,
    CompletedHabitsTable,
    PointsSpendLedger,
    RewardsPurchasedTable,
    RewardsTable,
    PendingRewardsTable,
    AiProcessedGratitudesTable,
    AiGeneratedMotivationsTable,
    FeedReactionsTable,
    FeedCommentsTable,
)
from Server.ai_utils import generate_motivation, generate_habit, OPENAI_MODEL, PROMPT_VERSION

from Server.utils import compute_points, potential_points_for_habit, parse_local_day, month_bounds, date_range_inclusive, local_midnight_to_utc, start_of_week, end_of_week, _day_start_utc, _normalize_schedule, habit_active_on_day

# ----------- CONTROL FLAGS / DEFAULTS --------- #
LAZY_SESSION_CLEANUP = True # If there is no cron or watcher process to remove stale sessions, do it on each successful login
api = Blueprint('api', __name__, url_prefix='/api')

MOTIVATION_MIN_INTERVAL = timedelta(minutes=5) # timeout ono AI motivation gen
AI_HABIT_MIN_INTERVAL = timedelta(seconds=30) # timeout on AI habit gen
FOCUS_CAT_MULTIPLIER = 2 # Multiplier given to 'focused' category

FULL_SCHEDULE = [0,1,2,3,4,5,6] # For simple recurring habits, they recur every day



# ----------- 🍪🍪🍪 COOKIE CONFIG 🍪🍪🍪 ----------- #
SESSION_COOKIE_NAME = "hab_life_sesh"
SESSION_LIFETIME = timedelta(hours=168)
COOKIE_SAMESITE = "Lax"
COOKIE_SECURE = True 
COOKIE_HTTPONLY = True

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

# ----------- 🍪🍪🍪 END 🍪🍪🍪 ----------- #

def _now_utc():
    return datetime.now(timezone.utc)

def _as_aware_utc(dt):
    # MySQL DATETIME comes back naive; treat it as UTC
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def today_local_date(tzname: str):
    return datetime.now(ZoneInfo(tzname)).date()

def serialize_reflection(row_map):
    if not row_map:
        return None
    d = dict(row_map)  # RowMapping -> dict
    # Stringify date/datetime for JSON
    for k in ("day_local", "created_at_utc", "updated_at_utc"):
        v = d.get(k)
        if v is not None:
            # date/datetime both have .isoformat()
            d[k] = v.isoformat()
    return d

def _week_start_end(d: date):  # Sun..Sat, inclusive
    # Mon=0..Sun=6 -> Sunday offset:
    sunday_offset = (d.weekday() + 1) % 7
    start = d - timedelta(days=sunday_offset)
    end = start + timedelta(days=6)
    return start, end

def _month_start_end(d: date):
    days = monthrange(d.year, d.month)[1]
    return date(d.year, d.month, 1), date(d.year, d.month, days)

def _to_user_local(dt, user_tz):
    """
    Convert a datetime from UTC to the user's timezone for non-habit events.

    - Habits: completed_at_local is already stored in the user's local time;
      we return it unchanged.
    - Rewards/reflections/comments: *_at_utc is stored as UTC; we convert.
    """
    if dt is None:
        return None

    # Everything else is stored as UTC (naive or tz-aware)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.astimezone(user_tz)

def _friendship_to_dict(row, me_id: int):
    """
    row: Mapping from FriendsTable (via .mappings()).
    me_id: current user id for directionality.
    """
    direction = "outgoing" if row["friending_user_id"] == me_id else "incoming"
    other_id = (
        row["friended_user_id"]
        if direction == "outgoing"
        else row["friending_user_id"]
    )

    return {
        "id": row["friendship_id"],
        "friending_user_id": row["friending_user_id"],
        "friended_user_id": row["friended_user_id"],
        "other_user_id": other_id,
        "status": row["status"],
        "direction": direction,
        "message": row["message"],
        "created_at_utc": row["created_at_utc"].isoformat()
        if row["created_at_utc"]
        else None,
        "updated_at_utc": row["updated_at_utc"].isoformat()
        if row["updated_at_utc"]
        else None
    }

def _are_friends(conn, u1: int, u2: int) -> bool:
    """
    Lightweight friendship check (accepted in either direction).
    """
    if u1 == u2:
        return True
    row = conn.execute(
        select(FriendsTable.c.status)
        .where(
            or_(
                and_(
                    FriendsTable.c.friending_user_id == u1,
                    FriendsTable.c.friended_user_id == u2,
                ),
                and_(
                    FriendsTable.c.friending_user_id == u2,
                    FriendsTable.c.friended_user_id == u1,
                ),
            )
        )
        .limit(1)
    ).first()
    return bool(row and getattr(row, "status", row[0]) == "accepted")

def _resolve_category_for_user(conn, user_id: int, category_id: int | None):
    """
    Ensure a category exists for the given user.
    - If category_id is provided, validate it belongs to the user.
    - Otherwise return the user's default (or first) category.
    """
    if category_id:
        row = conn.execute(
            select(CategoriesTable.c.id, CategoriesTable.c.points_mode)
            .where(
                and_(
                    CategoriesTable.c.id == category_id,
                    CategoriesTable.c.user_id == user_id,
                )
            )
            .limit(1)
        ).mappings().first()
        if not row:
            raise ValueError("category_not_found")
        return row

    row = conn.execute(
        select(CategoriesTable.c.id, CategoriesTable.c.points_mode)
        .where(CategoriesTable.c.user_id == user_id)
        .order_by(CategoriesTable.c.is_default.desc(), CategoriesTable.c.id.asc())
        .limit(1)
    ).mappings().first()
    if not row:
        raise ValueError("no_categories")
    return row

def _shape_pending_habit_payload(raw: dict, recipient_id: int, creator_id: int, conn):
    """
    Validate and normalize habit fields for pending send/accept flows.
    """
    name = (raw.get("name") or "").strip()
    if not name:
        raise ValueError("name required")

    htype = raw.get("habit_type") or raw.get("type") or "recurring"
    if htype not in ("one-off", "recurring"):
        raise ValueError("invalid type")

    date_local = raw.get("date_local") if htype == "one-off" else None

    challenge = raw.get("challenge") or "easy"
    if challenge not in ("automatic", "easy", "difficult", "hard", "daunting"):
        raise ValueError("invalid challenge")

    importance = int(raw.get("importance") or 1)
    if importance not in (1, 2, 3):
        raise ValueError("invalid importance")

    base_value = float(raw.get("base_value") or 1.0)
    time_minutes = (
        int(raw.get("time_minutes"))
        if raw.get("time_minutes") is not None
        else None
    )
    percent_target = (
        float(raw.get("percent_target"))
        if raw.get("percent_target") is not None
        else None
    )

    raw_instances = raw.get("instances")
    if raw_instances is None or raw_instances == "":
        instances = 1
    else:
        try:
            instances = int(raw_instances)
        except ValueError:
            raise ValueError("instances must be an integer")
        if instances < 1 or instances > 10:
            raise ValueError("instances must be between 1 and 10")

    schedule = None
    if htype == "recurring":
        try:
            schedule = _normalize_schedule(raw.get("schedule"))
        except ValueError:
            schedule = FULL_SCHEDULE

    cat_id = raw.get("category_id")
    cat = _resolve_category_for_user(conn, recipient_id, cat_id)

    if cat["points_mode"] == "time" and time_minutes is None:
        raise ValueError("time_minutes required for time mode")
    if cat["points_mode"] == "percent" and percent_target is None:
        raise ValueError("percent_target required for percent mode")

    now = datetime.utcnow()
    return {
        "user_id": recipient_id,
        "creator_user_id": creator_id,
        "category_id": cat["id"],
        "name": name,
        "type": htype,
        "date_local": date_local,
        "challenge": challenge,
        "importance": importance,
        "base_value": base_value,
        "time_minutes": time_minutes,
        "percent_target": percent_target,
        "schedule": schedule,
        "notes": (raw.get("notes") or None),
        "active": 1,
        "ai_created": bool(raw.get("ai_created")),
        "instances": instances,
        "created_at_utc": now,
        "updated_at_utc": now,
    }

def _shape_pending_reward_payload(raw: dict, recipient_id: int, creator_id: int):
    name = (raw.get("name") or "").strip()
    cost = raw.get("cost_points")
    if not name or cost is None:
        raise ValueError("name and cost_points required")
    now = datetime.utcnow()
    return {
        "user_id": recipient_id,
        "creator_user_id": creator_id,
        "name": name,
        "emoji": raw.get("emoji") or "🎁",
        "color": raw.get("color") or "#E5E7EB",
        "cost_points": float(cost),
        "note": (raw.get("note") or "").strip() or None,
        "is_recurring": 1 if raw.get("is_recurring") else 0,
        "active": 1,
        "created_at_utc": now,
    }

def _pending_row_to_dict(row, item_type: str):
    """
    Normalize a pending habit/reward row (with joined user fields) for JSON.
    """
    created_at = row.get("created_at_utc")
    base = {
        "type": item_type,
        "id": row["id"],
        "user_id": row.get("user_id"),
        "creator_user_id": row.get("creator_user_id"),
        "created_at_utc": created_at.isoformat() if created_at else None,
        "recipient": {
            "id": row.get("user_id"),
            "name": row.get("recipient_username"),
            "emoji": row.get("recipient_emoji"),
            "color": row.get("recipient_color"),
        },
        "creator": {
            "id": row.get("creator_user_id"),
            "name": row.get("creator_username"),
            "emoji": row.get("creator_emoji"),
            "color": row.get("creator_color"),
        },
    }
    if item_type == "habit":
        base.update(
            {
                "name": row.get("name"),
                "category_id": row.get("category_id"),
                "type_label": row.get("type"),
                "category_emoji": row.get("category_emoji"),
                "category_color": row.get("category_color"),
                "category_points_mode": row.get("category_points_mode"),
                "date_local": row.get("date_local").isoformat() if row.get("date_local") else None,
                "challenge": row.get("challenge"),
                "importance": int(row.get("importance") or 0),
                "base_value": float(row.get("base_value") or 0),
                "time_minutes": row.get("time_minutes"),
                "percent_target": float(row.get("percent_target")) if row.get("percent_target") is not None else None,
                "schedule": row.get("schedule"),
                "notes": row.get("notes"),
                "instances": int(row.get("instances") or 1),
            }
        )
    else:
        base.update(
            {
                "name": row.get("name"),
                "emoji": row.get("emoji"),
                "color": row.get("color"),
                "cost_points": float(row.get("cost_points") or 0),
                "note": row.get("note"),
                "is_recurring": bool(row.get("is_recurring")),
            }
        )
    return base

def _pending_select(table):
    return _pending_select_with_category(table, include_category=False)

def _pending_select_with_category(table, include_category=False):
    recipient = UsersTable.alias("recipient")
    creator = UsersTable.alias("creator")
    columns = [
        table,
        recipient.c.username.label("recipient_username"),
        recipient.c.emoji.label("recipient_emoji"),
        recipient.c.accent_color.label("recipient_color"),
        creator.c.username.label("creator_username"),
        creator.c.emoji.label("creator_emoji"),
        creator.c.accent_color.label("creator_color"),
    ]

    cat = CategoriesTable.alias("pending_category")
    if include_category:
        columns.extend(
            [
                cat.c.emoji.label("category_emoji"),
                cat.c.color.label("category_color"),
                cat.c.points_mode.label("category_points_mode"),
            ]
        )

    stmt = (
        select(*columns)
        .select_from(
            table.join(recipient, table.c.user_id == recipient.c.id).outerjoin(
                creator, table.c.creator_user_id == creator.c.id
            )
        )
    )
    if include_category:
        stmt = stmt.outerjoin(cat, table.c.category_id == cat.c.id)
    return stmt

def get_user_from_post(conn, feed_kind: str, item_id: int) -> int:
    """
    Given a feed_kind ('habit' | 'reward' | 'reflection')
    and the underlying item_id, return the owning user_id.

    Raises ValueError if the feed_kind is invalid or the item is not found.
    """
    if feed_kind == "habit":
        stmt = select(CompletedHabitsTable.c.user_id).where(CompletedHabitsTable.c.id == item_id)
    elif feed_kind == "reward":
        stmt = select(RewardsTable.c.user_id).where(RewardsTable.c.id == item_id)
    elif feed_kind == "reflection":
        stmt = select(ReflectionsTable.c.user_id).where(ReflectionsTable.c.id == item_id)
    else:
        raise ValueError(f"invalid feed_kind: {feed_kind!r}")

    row = conn.execute(stmt).first()
    if not row:
        raise ValueError(f"{feed_kind} with id={item_id} not found")

    # row can be a Row with .user_id or a tuple depending on version
    return getattr(row, "user_id", row[0])


def build_feed_preview(conn, feed_kind: str, item_id: int) -> dict:
    """
    Build a small 'feed-like' preview for a given post.
    Returns a dict shaped similarly to FriendFeed items, but minimal.
    """
    if feed_kind == "habit":
        stmt = (
            select(
                CompletedHabitsTable.c.id,
                CompletedHabitsTable.c.name_snapshot,
                CompletedHabitsTable.c.created_at_utc,
                CompletedHabitsTable.c.id.label("owner_id"),
                UsersTable.c.username.label("owner_username"),
                UsersTable.c.emoji.label("owner_emoji"),
                UsersTable.c.accent_color.label("owner_color"),
            )
            .select_from(CompletedHabitsTable.join(UsersTable, CompletedHabitsTable.c.user_id == UsersTable.c.id))
            .where(CompletedHabitsTable.c.id == item_id)
        )
        row = conn.execute(stmt).mappings().first()
        if not row:
            return None

        return {
            "feed_kind": feed_kind,
            "feed_item_id": item_id,
            "username": row["owner_username"],
            "emoji": row["owner_emoji"],
            "user_color": row["owner_color"],
            "accent_color": row["owner_color"],  # re-use user color as card bg
            "title": row["name_snapshot"],
            "subtitle": "",
            "points_delta": None,
            "event_time": row["created_at_utc"].isoformat() if row["created_at_utc"] else None,
        }

    elif feed_kind == "reward":
        stmt = (
            select(
                RewardsTable.c.id,
                RewardsTable.c.name,
                RewardsTable.c.created_at_utc,
                UsersTable.c.id.label("owner_id"),
                UsersTable.c.username.label("owner_username"),
                UsersTable.c.emoji.label("owner_emoji"),
                UsersTable.c.accent_color.label("owner_color"),
            )
            .select_from(RewardsTable.join(UsersTable, RewardsTable.c.user_id == UsersTable.c.id))
            .where(RewardsTable.c.id == item_id)
        )
        row = conn.execute(stmt).mappings().first()
        if not row:
            return None

        return {
            "feed_kind": feed_kind,
            "feed_item_id": item_id,
            "username": row["owner_username"],
            "emoji": row["owner_emoji"],
            "user_color": row["owner_color"],
            "accent_color": "#FEF3C7",  # match reward badge bg
            "title": row["name"],
            "subtitle": "",
            "points_delta": None,
            "event_time": row["created_at_utc"].isoformat() if row["created_at_utc"] else None,
        }

    elif feed_kind == "reflection":
        stmt = (
            select(
                ReflectionsTable.c.id,
                ReflectionsTable.c.created_at_utc,
                ReflectionsTable.c.day_local,
                UsersTable.c.id.label("owner_id"),
                UsersTable.c.username.label("owner_username"),
                UsersTable.c.emoji.label("owner_emoji"),
                UsersTable.c.accent_color.label("owner_color"),
            )
            .select_from(ReflectionsTable.join(UsersTable, ReflectionsTable.c.user_id == UsersTable.c.id))
            .where(ReflectionsTable.c.id == item_id)
        )
        row = conn.execute(stmt).mappings().first()
        if not row:
            return None

        # prefer explicit title; fall back to trimmed body
        title = f"Reflection on {row["day_local"]}"

        return {
            "feed_kind": feed_kind,
            "feed_item_id": item_id,
            "username": row["owner_username"],
            "emoji": row["owner_emoji"],
            "user_color": row["owner_color"],
            "accent_color": "#EEF2FF",
            "title": title,
            "subtitle": "",
            "points_delta": None,
            "event_time": row["created_at_utc"].isoformat() if row["created_at_utc"] else None,
        }

    else:
        return None


############################ BEGIN APP SERVER ############################


load_dotenv()

def _make_engine():
    # Option A: URL from env
    db_url = os.getenv("DB_URL")
    if db_url:
        return create_engine(db_url, pool_pre_ping=True, pool_recycle=1800, future=True)

    # Option B: ~/.my.cnf
    cnf = os.getenv("MYSQL_CNF")
    if cnf:
        return create_engine(
            "mysql+pymysql://",
            connect_args={"read_default_file": cnf, "read_default_group": "client"},
            pool_pre_ping=True, pool_recycle=1800, future=True
        )

    raise RuntimeError("No DB config found. Set DB_URL or MYSQL_CNF in .env")

def create_app():
    app = Flask(__name__)

    # --- CORS allowlist ---
    origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS","").split(",") if o.strip()]
    CORS(app, resources={r"/*": {"origins": origins or ["https://app-dev.samellgass.com"]}}, methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
     supports_credentials=True)

    # --- DB engine ---
    engine = _make_engine()
    app.extensions = getattr(app, "extensions", {})
    app.extensions["engine"] = engine

    def _clear_expired_sessions():
        with engine.begin() as conn:
            res = conn.execute(delete(SessionsTable).where(SessionsTable.c.expires_at < _now_utc()))
            print("Cleared expired session tokens. {} rows were removed.".format(res.rowcount))

    def ensure_default_category(conn, user_id: int):
        row = conn.execute(
            select(CategoriesTable.c.id).where(
                (CategoriesTable.c.user_id == user_id) &
                (CategoriesTable.c.is_default == True)
            )
        ).first()
        if row: return row[0]
        return create_default_categories(conn, user_id)
    
    def create_default_categories(conn, user_id: int):
        res = conn.execute(insert(CategoriesTable).values(
            user_id=user_id,
            category_name="one-offs",
            emoji="🎯",
            color="#E5E7EB",
            points_mode="tasks",
            is_default=True,
            created_at_utc=datetime.utcnow(),
            updated_at_utc=datetime.utcnow(),
        ))
        return res.inserted_primary_key[0]
    
    def create_defaults_for_new_user(conn, uid):
        # TODO: as we add more functionality, add for user here.
        # For now, just create the default category(s)
        create_default_categories(conn, uid)

    def _points_available_for_habit_on_day(row, day_local, tzname):
        """
        Compute how many *potential* points this habit contributes
        to `day_local` in the user's timezone. Returns 0.0 if the
        habit is not active / scheduled that day.
        """

        # Never count a day strictly before creation.
        created = row.get("created_at_utc")
        if created is not None:
            day_end_utc = _day_start_utc(day_local, tzname) + timedelta(days=1)
            if created > day_end_utc:
                return 0.0

        if row["type"] == "recurring":
            # Recurring habits must be active and on schedule today.
            if row.get("active") != 1:
                return 0.0
            if not habit_active_on_day(row, day_local, tzname):
                return 0.0
        else:
            # One-offs only count on their exact date_local (regardless of active).
            if row.get("date_local") != day_local:
                return 0.0

        # Compute potential points (including focus multiplier if any).
        return float(
            potential_points_for_habit(
                row["points_mode"],
                row["base_value"],
                row["challenge"],
                row["importance"],
                time_target=row["time_minutes"],
                percent_target=row["percent_target"],
                is_focused=bool(row.get("is_focused")),
            ) or 0.0
        )


    # --- User Login + Cookie Handling --- #
    @app.before_request
    def load_current_user():
        g.user = None
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if not token:
            return
        tok_hash = _hash_token(token) # toke hash? don't mind if I do!
        with engine.connect() as conn:
            row = conn.execute(
                select(UsersTable.c.id, UsersTable.c.username, UsersTable.c.timezone, SessionsTable.c.expires_at, 
                       UsersTable.c.emoji, UsersTable.c.accent_color)
                .select_from(SessionsTable.join(UsersTable, SessionsTable.c.user_id == UsersTable.c.id))
                .where(SessionsTable.c.token_hash == tok_hash)
            ).mappings().first()
        if not row:
            return
        # check expiry
        if _as_aware_utc(row["expires_at"]) < _now_utc():
            return
        g.user = {"id": row.id, "username": row.username, "timezone": row.timezone or "UTC", "emoji": row.emoji, "accent_color": row.accent_color}

    def login_required(fn):
        """Creates a decorator to be placed on functions requiring a login to automatically handle
        sending back an unauthorized response when the session is not authenticated"""
        from functools import wraps
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not g.user:
                return jsonify(error="unauthorized"), 401
            return fn(*args, **kwargs)
        return wrapper

    @api.get("/healthz")
    def healthz():
        return jsonify(ok=True)
    
    @api.post("/db/init")
    def initialize_db():
        create_all_tables(engine)
        return jsonify(successful=True)


    @api.post("/users")
    def attempt_to_create_new_user():
        # Get username and password from the request and hash the password if only password1 is provided
        # If password 2 is provided, additionally ensure they match
        payload = request.get_json(force=True)
        username = payload.get("username", "").strip()
        password = payload.get("password", "").strip()
        password2 = payload.get("password2", password)
        if not username or not password:
            return jsonify(error="username or password not supplied"), 400
        if password != password2:
            return jsonify(error="the passwords do not match 🤓"), 400
        
        pw_hash = generate_password_hash(password)

        try:
            with engine.begin() as conn:
                result = conn.execute(
                    insert(UsersTable).values(
                        username=username,
                        password_hash=pw_hash
                    )
                )
                user_id = result.inserted_primary_key[0]

                # Create defaults for new user
                create_defaults_for_new_user(conn, user_id)

            return jsonify(userId=user_id, username=username)
        except SQLAlchemyError as e:
            print("Encountered exception {} attempting to create user from payload {}".format(e, payload))
            # something went wrong: check uniqueness of username
            with engine.connect() as conn:
                count = conn.execute(
                    select(func.count()).select_from(UsersTable).where(UsersTable.c.username == username)
                ).scalar_one()

            if count == 1:
                return jsonify(error="username {} already exists".format(username)), 409
            else:
                # log the real exception server-side for debugging
                app.logger.exception("Unexpected error during user creation")
                return jsonify(error="something went wrong"), 500
            
    @api.post('/auth/login')
    def attempt_to_login_user():
        payload = request.get_json(force=True)
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        if not username or not password:
            return jsonify(error="username and password are required"), 400

        with engine.connect() as conn:
            row = conn.execute(
                select(UsersTable.c.id, UsersTable.c.password_hash).where(UsersTable.c.username == username)
            ).mappings().first()
        if not row or not check_password_hash(row["password_hash"], password):
            return jsonify(error="invalid credentials"), 401

        # create session
        raw_token = secrets.token_urlsafe(32)  # ~256 bits
        tok_hash = _hash_token(raw_token)
        now = datetime.utcnow()
        exp = now + SESSION_LIFETIME
        with engine.begin() as conn:
            conn.execute(insert(SessionsTable).values(
                user_id=row["id"],
                token_hash=tok_hash,
                created_at=now,
                expires_at=exp,
                user_agent=request.headers.get("User-Agent")[:256] if request.headers.get("User-Agent") else None,
                ip=request.headers.get("X-Forwarded-For") or request.remote_addr
            ))

            # TODO: REMOVE THIS LATER: CREATES DEFAULT CATEGORY ON FIRST LOGIN. 
            ensure_default_category(conn, row["id"])

        max_age = int(SESSION_LIFETIME.total_seconds())
        resp = jsonify(ok=True, userId=row["id"])
        resp.set_cookie(
            SESSION_COOKIE_NAME, raw_token,
            max_age=max_age, httponly=COOKIE_HTTPONLY, secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE, path="/"
        )

        if LAZY_SESSION_CLEANUP:
            _clear_expired_sessions()
            # TODO: TAKE THIS OUT LATER - 
        return resp
    
    @api.post('/auth/logout')
    def attempt_to_logout_user():
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if token:
            tok_hash = _hash_token(token)
            with engine.begin() as conn:
                conn.execute(delete(SessionsTable).where(SessionsTable.c.token_hash == tok_hash))
                # TODO: maybe differentiate between 'hey, no token existed' and 'cool, logging you out'

        resp = jsonify(ok=True)
        resp.set_cookie(SESSION_COOKIE_NAME, "", expires=0, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, path="/")
            
        return resp

    @api.get("/auth/me")
    def auth_me():
        if not g.user:
            return jsonify(authenticated=False), 200
        return jsonify(authenticated=True, user=g.user), 200

    # ---- ALL ROUTES THAT REQUIRE PREVIOUS AUTHENTICATION ------ #
    @api.get("/me/profile")
    @login_required
    def get_profile():
        with app.extensions["engine"].connect() as c:
            row = c.execute(
                select(UsersTable.c.id, UsersTable.c.username, UsersTable.c.emoji, UsersTable.c.accent_color)
                .where(UsersTable.c.id == g.user["id"])
            ).mappings().first()
        return jsonify(
            id=row["id"], username=row["username"],
            emoji=row.get("emoji"), accent_color=row.get("accent_color")
        ), 200
    
    @api.put("/me/profile")
    @login_required
    def update_profile():
        if not request.is_json:
            return jsonify(error="Expected JSON body"), 400

        data = request.get_json(silent=True) or {}
        emoji = (data.get("emoji") or "").strip() or None
        color = (data.get("accent_color") or "").strip() or None

        # Normalize: allow clearing either field
        if emoji and len(emoji) > 8:
            return jsonify(error="Emoji too long (max 8 bytes)."), 400

        # Accept hex (#RRGGBB) OR one of our pastel whitelist
        def is_hex6(s): 
            return isinstance(s, str) and len(s) == 7 and s[0] == '#' and all(c in "0123456789abcdefABCDEF" for c in s[1:])

        if color and not (is_hex6(color)):
            return jsonify(error="Unknown color. Use a hex like #AABBCC or one of the preset pastels."), 400

        with app.extensions["engine"].begin() as c:
            c.execute(
                update(UsersTable)
                .where(UsersTable.c.id == g.user["id"])
                .values(emoji=emoji, accent_color=color)
            )
            row = c.execute(
                select(UsersTable.c.id, UsersTable.c.username, UsersTable.c.emoji, UsersTable.c.accent_color)
                .where(UsersTable.c.id == g.user["id"])
            ).mappings().first()

        return jsonify(
            id=row["id"], username=row["username"],
            emoji=row["emoji"], accent_color=row["accent_color"]
        ), 200

    @api.post("/me/timezone")
    @login_required
    def set_timezone():
        tz = (request.json.get("timezone") or "").strip()
        ZoneInfo(tz)  # validate; raises if invalid
        with engine.begin() as c:
            c.execute(update(UsersTable).where(UsersTable.c.id==g.user["id"]).values(timezone=tz))
        return jsonify(ok=True, timezone=tz)

    @api.post("/daylogs")
    @login_required
    def create_or_update_daylog():
        # Expect: { summary, highs, lows, buffalos, mood, gratitude: [] }
        tzname = g.user.get("timezone") or "UTC"
        payload = request.get_json(force=True)
        user_id = g.user["id"]
        day_str = (payload.get("day") or "").strip()
        day_local = (datetime.strptime(day_str, "%Y-%m-%d").date() if day_str else today_local_date(tzname))

        now_utc= _now_utc()
        payload = {
            "summary":  (payload.get("summary") or "").strip() or None,
            "highs":    (payload.get("highs") or "").strip() or None,
            "lows":     (payload.get("lows") or "").strip() or None,
            "buffalos": (payload.get("buffalos") or "").strip() or None,
            "mood":     int(payload.get("mood")) if payload.get("mood") else None,
            "gratitude": payload.get("gratitude") if isinstance(payload.get("gratitude"), list) else None,
            "day_local": day_local,
            "updated_at_utc": now_utc,
        }

        with app.extensions["engine"].begin() as conn:
            existing = conn.execute(
                select(ReflectionsTable.c.id).where(
                    ReflectionsTable.c.user_id==user_id, ReflectionsTable.c.day_local==day_local
                )
            ).scalar()
            if existing:
                conn.execute(
                    update(ReflectionsTable).where(ReflectionsTable.c.id==existing).values(**payload)
                )
                rid = existing
                created = False
            else:
                res = conn.execute(
                    insert(ReflectionsTable).values(user_id=user_id, created_at_utc=now_utc, **payload)
                )
                rid = res.inserted_primary_key[0]
                created = True

        return jsonify(id=rid, created=created), (201 if created else 200)
    
    @api.get("/daylogs")
    @login_required
    def get_daylog():
        """Return the user's daylog for a given local calendar day if it exists."""
        day_str = request.args.get("day")
        if not day_str:
            return jsonify(error="day query param (YYYY-MM-DD) required"), 400

        try:
            # strict, no timezone: it's a user-local calendar day label
            d_local = datetime.strptime(day_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify(error="invalid day"), 400

        with app.extensions["engine"].connect() as conn:
            row = conn.execute(
                select(
                    ReflectionsTable.c.id, ReflectionsTable.c.day_local, ReflectionsTable.c.summary, ReflectionsTable.c.highs,
                    ReflectionsTable.c.lows, ReflectionsTable.c.buffalos, ReflectionsTable.c.mood, ReflectionsTable.c.gratitude
                ).where(
                    ReflectionsTable.c.user_id == g.user["id"],
                    ReflectionsTable.c.day_local == d_local
                )
            ).mappings().first()

        if not row:
            return jsonify(found=False), 404

        return jsonify(found=True, reflection=serialize_reflection(row)), 200


    @api.get("/calendar")
    @login_required
    def calendar_view():
        tzname = g.user.get("timezone") or "UTC"

        month_str = request.args.get("month", "").strip()  # YYYY-MM
        if month_str:
            try:
                y, m = map(int, month_str.split("-", 1))
            except Exception:
                return jsonify(error="invalid month (use YYYY-MM)"), 400
        else:
            t = today_local_date(tzname)
            y, m = t.year, t.month

        days_in_month = monthrange(y, m)[1]
        month_start = date(y, m, 1)
        month_end   = date(y, m, days_in_month)

        # base scaffold
        days = [{
            "date": date(y, m, d).isoformat(),
            "completed": False,
            "mood": None
        } for d in range(1, days_in_month + 1)]
        idx = { d["date"]: d for d in days }

        # fetch reflections keyed by local day
        with app.extensions["engine"].connect() as c:
            rows = c.execute(
                select(ReflectionsTable.c.day_local, ReflectionsTable.c.mood)
                .where(
                    and_(
                        ReflectionsTable.c.user_id == g.user["id"],
                        ReflectionsTable.c.day_local >= month_start,
                        ReflectionsTable.c.day_local <= month_end,
                    )
                )
            ).all()

        for d_local, mood in rows:
            key = d_local.isoformat()
            if key in idx:
                idx[key]["completed"] = True
                idx[key]["mood"] = int(mood) if mood is not None else None

        # last 7 days (local)
        today = today_local_date(tzname)
        # start of local week (Sunday)
        dow = today.weekday()           # Mon=0..Sun=6
        sunday_offset = (dow +1) % 7  # Sun=0, Mon=1, ...
        week_start = today - timedelta(days=sunday_offset)

        week = []
        with app.extensions["engine"].connect() as c:
            for i in range(7):  # Sun..Sat
                d = week_start + timedelta(days=i)
                mood = c.execute(
                    select(ReflectionsTable.c.mood).where(
                        and_(ReflectionsTable.c.user_id == g.user["id"],
                            ReflectionsTable.c.day_local == d)
                    )
                ).scalar()
                week.append({
                    "date": d.isoformat(),
                    "completed": mood is not None,
                    "mood": int(mood) if mood is not None else None
                })

        return jsonify({
            "month": f"{y:04d}-{m:02d}",
            "days": days,   # list of {date, completed, mood}
            "week": week    # last 7 days, local
        })
    
    @api.get("/ai/summary")
    @login_required
    def ai_summary():
        """
        GET /api/ai/summary?scope=day|week|month
        Returns: {scope, label, available, summary?, message?, today_has_reflection?}
        - day: still looks specifically for *yesterday* (local)
        - week/month: returns the MOST RECENT rollup for that scope (by target_date desc)
        """
        scope = (request.args.get("scope") or "day").lower()
        if scope not in ("day", "week", "month"):
            return jsonify(error="invalid scope"), 400

        tz = g.user.get("timezone") or "UTC"
        today_local = today_local_date(tz)

        # ----- DAY (exactly yesterday) -----
        if scope == "day":
            target_day = today_local - timedelta(days=1)  # yesterday (local)
            label = "Yesterday"
            with app.extensions["engine"].connect() as c:
                ai = c.execute(
                    select(AiProcessedReflectionsTable.c.summary)
                    .where(and_(
                        AiProcessedReflectionsTable.c.user_id == g.user["id"],
                        AiProcessedReflectionsTable.c.scope == "day",
                        AiProcessedReflectionsTable.c.kind == "summary",
                        AiProcessedReflectionsTable.c.target_date == target_day,
                    ))
                ).scalar()

                if ai:
                    return jsonify(scope="day", label=label, available=True, summary=ai), 200

                # no AI yet — check if user logged *today* (to craft friendlier message)
                today_row = c.execute(
                    select(ReflectionsTable.c.id)
                    .where(and_(
                        ReflectionsTable.c.user_id == g.user["id"],
                        ReflectionsTable.c.day_local == today_local
                    ))
                ).scalar()

            if today_row:
                msg = "You didn't enter a reflection yesterday. But you did today, so check back tomorrow!"
                return jsonify(scope="day", label=label, available=False, message=msg, today_has_reflection=True), 200
            else:
                msg = "You didn't enter a reflection yesterday. If you want to see a summary for tomorrow, enter one today!"
                return jsonify(scope="day", label=label, available=False, message=msg, today_has_reflection=False), 200

        # ----- WEEK / MONTH: return MOST RECENT rollup -----
        # We keyed weekly/monthly rollups by (user_id, scope, kind, target_date=end_of_window).
        # So just take the latest target_date for that scope.
        with app.extensions["engine"].connect() as c:
            row = c.execute(
                select(
                    AiProcessedReflectionsTable.c.summary,
                    AiProcessedReflectionsTable.c.target_date
                )
                .where(and_(
                    AiProcessedReflectionsTable.c.user_id == g.user["id"],
                    AiProcessedReflectionsTable.c.scope == scope,
                    AiProcessedReflectionsTable.c.kind == "summary",
                ))
                .order_by(AiProcessedReflectionsTable.c.target_date.desc())
                .limit(1)
            ).mappings().first()

        if not row:
            return jsonify(
                scope=scope,
                label=("This Week" if scope == "week" else "This Month"),
                available=False,
                message=f"No {scope} summary yet. It will appear once that rollup is generated."
            ), 200

        # Build a helpful label using the record’s target_date:
        # - for week: target_date is the Sunday (end of Mon..Sun window) — show range
        # - for month: target_date is the last day of the month — show month name
        td = row["target_date"]
        if scope == "week":
            end_day = td
            start_day = td - timedelta(days=6)
            label = f"Week ({start_day.isoformat()} – {end_day.isoformat()})"
        else:
            # last day of the month; show month name + year
            label = f"{td.strftime('%B %Y')}"

        return jsonify(
            scope=scope,
            label=label,
            available=True,
            summary=row["summary"],
        ), 200

        

    @api.get("/habits")
    @login_required
    def list_habits():
        when = request.args.get("when")
        if not when:
            return jsonify(error="missing ?when"), 400
        
        try:
            y, m, d = map(int, when.split("-"))
            day_local = date(y, m, d)
        except Exception:
            return jsonify(error="invalid ?when"), 400
        
        tzname = g.user.get("timezone") or "UTC"
        day_start_utc = _day_start_utc(day_local, tzname)
        day_end_utc   = day_start_utc + timedelta(days=1)

        creator = UsersTable.alias("creator_habits")
        creator_cols = [
            creator.c.username.label("creator_username"),
            creator.c.emoji.label("creator_emoji"),
            creator.c.accent_color.label("creator_color"),
        ]

        with app.extensions["engine"].connect() as c:
            # common column set
            cols = [
                HabitsTable.c.id, HabitsTable.c.name, HabitsTable.c.type, HabitsTable.c.date_local,
                HabitsTable.c.base_value, HabitsTable.c.challenge, HabitsTable.c.importance, HabitsTable.c.schedule,
                HabitsTable.c.time_minutes, HabitsTable.c.percent_target,
                HabitsTable.c.created_at_utc, HabitsTable.c.instances,
                CategoriesTable.c.emoji, CategoriesTable.c.color, CategoriesTable.c.points_mode, CategoriesTable.c.is_focused
            ]

            rec_all = c.execute(
                    select(*cols, *creator_cols)
                    .select_from(
                        HabitsTable
                        .join(CategoriesTable, HabitsTable.c.category_id == CategoriesTable.c.id)
                        .outerjoin(creator, HabitsTable.c.creator_user_id == creator.c.id)
                    )
                    .where(and_(
                        HabitsTable.c.user_id == g.user["id"], 
                        HabitsTable.c.active == 1, 
                        HabitsTable.c.type == "recurring",
                        HabitsTable.c.created_at_utc <= day_end_utc
                    ))
                    .order_by(HabitsTable.c.created_at_utc.desc())
                ).mappings().all()
            
            # For recurring habits, filter by scheduled recurrence
            rec = [r for r in rec_all if habit_active_on_day(r, day_local, tzname)]


            one = c.execute(
                select(*cols, *creator_cols)
                .select_from(
                    HabitsTable
                    .join(CategoriesTable, HabitsTable.c.category_id == CategoriesTable.c.id)
                    .outerjoin(creator, HabitsTable.c.creator_user_id == creator.c.id)
                )
                .where(and_(
                    HabitsTable.c.user_id == g.user["id"], 
                    HabitsTable.c.active == 1,
                    HabitsTable.c.type == "one-off", 
                    HabitsTable.c.date_local == day_local,
                    HabitsTable.c.created_at_utc <= day_end_utc
                            ))
                .order_by(HabitsTable.c.created_at_utc.desc())
            ).mappings().all()

            done_rows = c.execute(
                select(
                    CompletedHabitsTable.c.habit_id,
                    func.count().label("completed_instances"),
                )
                .where(
                    and_(
                        CompletedHabitsTable.c.user_id == g.user["id"],
                        CompletedHabitsTable.c.day_local == day_local,
                    )
                )
                .group_by(CompletedHabitsTable.c.habit_id)
            ).all()

            # 'done_counts' now represents the number of instances of a habit that have been completed
            done_counts = {
                hid: int(count)
                for (hid, count) in done_rows
                if hid is not None
            }

        def sort_key(r):
            instances = r.get("instances") or 1
            completed_instances = done_counts.get(r["id"], 0)

            # 1) COMPLETION: incomplete first: furthest from completion on top
            completed_percent = completed_instances / instances

            # 2) FOCUS AREA: focused first
            focus_key = 0 if bool(r["is_focused"]) else 1

            # 3) POTENTIAL_POINTS: most valuable habits first
            points_value = -1 * potential_points_for_habit(
                r["points_mode"],
                r["base_value"], r["challenge"], r["importance"],
                time_target=r["time_minutes"], percent_target=r["percent_target"],
                is_focused=bool(r["is_focused"]),
            )

            # 4) CREATED AT: newest first (desc) → negate timestamp for ascending sort
            ca = r.get("created_at_utc")
            created_key = -ca.timestamp() if ca is not None else float("-inf")
            return (completed_percent, focus_key, points_value, created_key)

        # combine raw rows, then filter and sort
        all_rows = [*one, *rec]
        rows_sorted = sorted(all_rows, key=sort_key)
        
        def shape(r):
            pm = r["points_mode"]
            instances = r.get("instances") or 1
            completed_instances = done_counts.get(r["id"], 0)

            pp = potential_points_for_habit(
                pm,
                r["base_value"], r["challenge"], r["importance"],
                time_target=r["time_minutes"], percent_target=r["percent_target"],
                is_focused=bool(r["is_focused"]),
            )

            # Fully complete when completed_instances >= instances
            fully_complete = completed_instances >= instances

            return {
                "id": r["id"],
                "name": r["name"],
                "type": r["type"],
                "date_local": r["date_local"].isoformat() if r["date_local"] else None,
                "category": {
                    "emoji": r["emoji"],
                    "color": r["color"],
                    "is_focused": bool(r["is_focused"]),
                },
                "points_mode": pm,
                "potential_points": pp,
                "completed_today": fully_complete,  # disable button when fully complete
                "time_minutes": r["time_minutes"],
                "percent_target": r["percent_target"],

                # NEW: instance-awareness for the UI
                "instances": int(instances),
                "completed_instances": int(completed_instances),

                # Shared items metadata
                "creator_username": r.get("creator_username"),
                "creator_emoji": r.get("creator_emoji"),
                "creator_color": r.get("creator_color"),
            }


        habits = [*map(shape, rows_sorted)]
        return jsonify(habits=habits), 200
    
    @api.get("/habits/<int:hid>")
    @login_required
    def get_habit(hid):
        uid = g.user["id"]
        creator = UsersTable.alias("creator_habit_single")
        with app.extensions["engine"].connect() as c:
            row = c.execute(
                select(
                    HabitsTable.c.id,
                    HabitsTable.c.name,
                    HabitsTable.c.category_id,
                    HabitsTable.c.type,
                    HabitsTable.c.date_local,
                    HabitsTable.c.challenge,
                    HabitsTable.c.importance,
                    HabitsTable.c.time_minutes,
                    HabitsTable.c.percent_target,
                    HabitsTable.c.schedule,
                    HabitsTable.c.instances,
                    CategoriesTable.c.points_mode,
                    creator.c.username.label("creator_username"),
                    creator.c.emoji.label("creator_emoji"),
                    creator.c.accent_color.label("creator_color"),
                )
                .select_from(
                    HabitsTable
                    .join(CategoriesTable)
                    .outerjoin(creator, HabitsTable.c.creator_user_id == creator.c.id)
                )
                .where(and_(
                    HabitsTable.c.id == hid,
                    HabitsTable.c.user_id == uid
                ))
                .limit(1)
            ).first()

            if not row:
                return jsonify(error="habit not found"), 404

            habit = dict(row._mapping)

        return jsonify({ "habit": habit })

    @api.get("/today/summary")
    @login_required
    def today_summary():
        day = request.args.get("day", "", type=str).strip()
        if not day:
            return jsonify(error="missing ?day"), 400
        try:
            day_local = datetime.strptime(day, "%Y-%m-%d").date()
        except Exception:
            return jsonify(error=f"invalid ?day: expected YYYY-MM-DD, got {day!r}"), 400
        
        tzname = g.user.get("timezone") or "UTC"
        day_start_utc = _day_start_utc(day_local, tzname)
        day_end_utc   = day_start_utc + timedelta(days=1)

        with app.extensions["engine"].connect() as c:
            # 1) Earned today (already correct)
            earned = c.execute(
                select(func.coalesce(func.sum(CompletedHabitsTable.c.points_awarded), 0))
                .where(and_(
                    CompletedHabitsTable.c.user_id == g.user["id"],
                    CompletedHabitsTable.c.day_local == day_local,
                ))
            ).scalar() or 0.0

            # 2) Denominator: ONLY habits relevant to this local day
            rows = c.execute(
                select(
                    HabitsTable.c.id,
                    HabitsTable.c.type,
                    HabitsTable.c.date_local,
                    HabitsTable.c.base_value,
                    HabitsTable.c.challenge,
                    HabitsTable.c.importance,
                    HabitsTable.c.time_minutes,
                    HabitsTable.c.percent_target,
                    HabitsTable.c.created_at_utc,
                    HabitsTable.c.schedule,          # 👈 needed for habit_active_on_day
                    HabitsTable.c.active,
                    CategoriesTable.c.points_mode,
                    CategoriesTable.c.is_focused,
                )
                .join(CategoriesTable, HabitsTable.c.category_id == CategoriesTable.c.id)
                .where(and_(
                    HabitsTable.c.user_id == g.user["id"],
                    or_(
                        # Recurring habits: only if still active
                        and_(HabitsTable.c.type == "recurring",
                             HabitsTable.c.active == 1),
                        # One-offs: include all with this exact local day,
                        # even if they were auto-archived after completion.
                        and_(HabitsTable.c.type == "one-off",
                             HabitsTable.c.date_local == day_local),
                    ),
                ))
            ).mappings().all()

        # Use the shared helper so logic matches /calendar/progress
        available = 0.0
        for r in rows:
            available += _points_available_for_habit_on_day(r, day_local, tzname)

        progress = (float(earned) / available) if available > 0 else 0.0
        return jsonify(
            earned_today=float(round(earned, 2)),
            available_today=float(round(available, 2)),
            progress=max(0.0, min(1.0, progress)),
        ), 200


    @api.post("/habits/<int:hid>/complete")
    @login_required
    def complete_habit(hid):
        tzname = g.user.get("timezone") or "UTC"
        data = request.get_json(silent=True) or {}

        with app.extensions["engine"].begin() as c:
            # Fetch habit + category (label columns explicitly)
            row = c.execute(
                select(
                    HabitsTable.c.id.label("h_id"),
                    HabitsTable.c.name.label("h_name"),
                    HabitsTable.c.type.label("h_type"),
                    HabitsTable.c.base_value.label("h_base"),
                    HabitsTable.c.challenge.label("h_chal"),
                    HabitsTable.c.importance.label("h_imp"),
                    HabitsTable.c.time_minutes.label("h_time_target"),
                    HabitsTable.c.percent_target.label("h_pct_target"),
                    HabitsTable.c.ai_created.label("h_ai_created"),
                    HabitsTable.c.instances.label("h_instances"),
                    CategoriesTable.c.id.label("cat_id"),
                    CategoriesTable.c.category_name.label("cat_name"),
                    CategoriesTable.c.points_mode.label("points_mode"),
                    CategoriesTable.c.is_focused.label("is_focused")
                )
                .join(CategoriesTable, HabitsTable.c.category_id == CategoriesTable.c.id)
                .where(
                    and_(
                        HabitsTable.c.id == hid,
                        HabitsTable.c.user_id == g.user["id"],
                        HabitsTable.c.active == 1,
                    )
                )
            ).mappings().first()

            if not row:
                return jsonify(error="habit not found"), 404

            pm = row["points_mode"]
            # Validate payload for mode
            if pm == "time":
                if data.get("time_minutes") is None:
                    return jsonify(error="time_minutes required for time mode"), 400
                time_minutes = int(data.get("time_minutes") or 0)
                percent_value = None
            elif pm == "percent":
                if data.get("percent_value") is None:
                    return jsonify(error="percent_value required for percent mode"), 400
                percent_value = float(data.get("percent_value") or 0)
                time_minutes = None
            else:  # tasks
                time_minutes = None
                percent_value = None

            # Local timestamps (user tz) + local day
            tz = g.user.get("timezone") or "UTC"
            now_local = datetime.now(ZoneInfo(tz)).replace(microsecond=0)

            # use historic date if provided, else today
            day_s = (data.get("day") or "").strip()
            if day_s:
                try:
                    y,m,dd = map(int, day_s.split("-"))
                    day_local = date(y,m,dd)
                except Exception:
                    return jsonify(error="invalid 'day' (use YYYY-MM-DD)"), 400
            else:
                day_local = today_local_date(tzname)

            today_local = today_local_date(tzname)

            if day_local > today_local:
                return jsonify(error="cannot complete future days"), 400

            # NOTE: prevent completion > num instances
            instances = row["h_instances"] or 1

            already = c.execute(
                select(func.count())
                .select_from(CompletedHabitsTable)
                .where(
                    and_(
                        CompletedHabitsTable.c.user_id == g.user["id"],
                        CompletedHabitsTable.c.habit_id == row["h_id"],
                        CompletedHabitsTable.c.day_local == day_local,
                    )
                )
            ).scalar() or 0
            if already >= instances:
                return jsonify(
                    error="already completed maximum instances for today",
                    instances=int(instances),
                    completed=int(already),
                ), 409

            # Compute points
            pts = compute_points(
                pm,
                row["h_base"],
                row["h_chal"],
                row["h_imp"],
                time_minutes=time_minutes,
                percent_value=percent_value,
                is_focused=row["is_focused"],
                instances=instances
            )

            # Write history
            c.execute(
                insert(CompletedHabitsTable).values(
                    user_id=g.user["id"],
                    habit_id=row["h_id"],
                    category_id=row["cat_id"],
                    name_snapshot=row["h_name"],
                    points_mode=pm,
                    challenge=row["h_chal"],
                    importance=row["h_imp"],
                    base_value=row["h_base"],
                    ai_created=row["h_ai_created"],
                    time_minutes=time_minutes,
                    percent_value=percent_value,
                    points_awarded=pts,
                    completed_at_local=now_local,
                    day_local=day_local,
                    created_at_utc=datetime.utcnow(),
                )
            )

            # Atomically bump earned
            c.execute(
                update(UsersTable)
                .where(UsersTable.c.id == g.user["id"])
                .values(points_earned=UsersTable.c.points_earned + pts)
            )

            # Auto-archive one-offs
            if row["h_type"] == "one-off":
                c.execute(
                    update(HabitsTable)
                    .where(HabitsTable.c.id == row["h_id"])
                    .values(active=0)
                )

            # Fresh totals for balance
            u = c.execute(
                select(UsersTable.c.points_earned, UsersTable.c.points_spent)
                .where(UsersTable.c.id == g.user["id"])
            ).mappings().first()

        balance = float(u["points_earned"] - u["points_spent"])
        return jsonify(ok=True, points_awarded=float(pts), balance=balance), 200

    @api.delete("/habits/<int:hid>")
    @login_required
    def delete_habit(hid):
        with app.extensions["engine"].begin() as c:
            # Verify habit belongs to user
            h = c.execute(
                select(HabitsTable.c.id, HabitsTable.c.user_id)
                .where(and_(HabitsTable.c.id == hid, HabitsTable.c.user_id == g.user["id"]))
            ).mappings().first()
            if not h:
                return jsonify(error="habit not found"), 404

            # Any completions exist?
            cnt = c.execute(
                select(func.count())
                .select_from(CompletedHabitsTable)
                .where(and_(CompletedHabitsTable.c.user_id == g.user["id"],
                            CompletedHabitsTable.c.habit_id == hid))
            ).scalar() or 0

            if cnt == 0:
                c.execute(delete(HabitsTable).where(HabitsTable.c.id == hid))
                kind = "hard"
            else:
                c.execute(update(HabitsTable).where(HabitsTable.c.id == hid).values(active=0))
                kind = "soft"

        return jsonify(ok=True, deleted=kind), 200
                
    @api.get("/categories")
    @login_required
    def list_categories():
        with app.extensions["engine"].connect() as c:
            rows = c.execute(
                select(CategoriesTable.c.id, CategoriesTable.c.category_name, CategoriesTable.c.emoji,
                    CategoriesTable.c.color, CategoriesTable.c.points_mode, CategoriesTable.c.is_default)
                .where(CategoriesTable.c.user_id == g.user["id"])
                .order_by(CategoriesTable.c.is_default.desc(), CategoriesTable.c.category_name.asc())
            ).mappings().all()
        return jsonify(categories=[dict(r) for r in rows]), 200
    
    @api.post("/categories")
    @login_required
    def create_category():
        data = request.get_json(silent=True) or {}
        name = (data.get("category_name") or "").strip()
        emoji = (data.get("emoji") or "").strip() or None
        color = (data.get("color") or "").strip() or None
        mode  = (data.get("points_mode") or "tasks").strip()
        if not name: return jsonify(error="category_name required"), 400
        if mode not in ("tasks","time","percent"): return jsonify(error="invalid points_mode"), 400
        now = datetime.utcnow()
        with app.extensions["engine"].begin() as c:
            res = c.execute(insert(CategoriesTable).values(
                user_id=g.user["id"], category_name=name, emoji=emoji, color=color,
                points_mode=mode, is_default=False, created_at_utc=now, updated_at_utc=now
            ))
            cid = res.inserted_primary_key[0]
            row = c.execute(select(CategoriesTable).where(CategoriesTable.c.id == cid)).mappings().first()
        return jsonify(id=row["id"], category_name=row["category_name"], emoji=row["emoji"],
                    color=row["color"], points_mode=row["points_mode"]), 200
    
    @api.post("/habits")
    @login_required
    def create_habit():
        d = request.get_json(silent=True) or {}
        name = (d.get("name") or "").strip()
        if not name: return jsonify(error="name required"), 400
        cat_id = d.get("category_id")
        if not cat_id: return jsonify(error="category_id required"), 400
        htype = d.get("type") or "recurring"
        if htype not in ("one-off","recurring"): return jsonify(error="invalid type"), 400
        date_local = d.get("date_local") if htype == "one-off" else None

        challenge = d.get("challenge") or "easy"
        if challenge not in ("automatic","easy","difficult","hard","daunting"):
            return jsonify(error="invalid challenge"), 400
        importance = int(d.get("importance") or 1)
        if importance not in (1,2,3): return jsonify(error="invalid importance"), 400

        base_value = float(d.get("base_value") or 1.0)
        time_minutes   = int(d.get("time_minutes")) if d.get("time_minutes") is not None else None
        percent_target = float(d.get("percent_target")) if d.get("percent_target") is not None else None

        ai_created = str(d.get("ai_created", False)).lower() == "true"

        raw_instances = d.get("instances")
        if raw_instances is None or raw_instances == "":
            instances = 1
        else:
            try:
                instances = int(raw_instances)
            except ValueError:
                return jsonify(error="instances must be an integer"), 400
            if instances < 1 or instances > 10:
                return jsonify(error="instances must be between 1 and 10"), 400

        schedule = None
        if htype == "recurring":
            try:
                schedule = _normalize_schedule(d.get("schedule"))
            except ValueError as e:
                schedule = FULL_SCHEDULE

        now = datetime.utcnow()
        with app.extensions["engine"].begin() as c:
            # check category belongs to user & get its mode
            cat = c.execute(select(CategoriesTable.c.id, CategoriesTable.c.points_mode)
                            .where((CategoriesTable.c.id == cat_id) & (CategoriesTable.c.user_id == g.user["id"]))
                        ).mappings().first()
            if not cat: return jsonify(error="category not found"), 404

            # sanity: mode-specific fields
            if cat["points_mode"] == "time":
                if time_minutes is None: return jsonify(error="time_minutes required for time mode"), 400
            if cat["points_mode"] == "percent":
                if percent_target is None: return jsonify(error="percent_target required for percent mode"), 400

            res = c.execute(insert(HabitsTable).values(
                user_id=g.user["id"], category_id=cat["id"], name=name, type=htype,
                date_local=date_local, challenge=challenge, importance=importance,
                base_value=base_value, time_minutes=time_minutes, percent_target=percent_target,
                schedule=schedule,instances=instances,
                active=1, ai_created=ai_created, created_at_utc=now, updated_at_utc=now
            ))
            hid = res.inserted_primary_key[0]
            row = c.execute(select(HabitsTable).where(HabitsTable.c.id == hid)).mappings().first()

        return jsonify(id=row["id"], name=row["name"], type=row["type"], date_local=row["date_local"]), 200

    @api.get("/points")
    @login_required
    def get_points():
        with app.extensions["engine"].connect() as c:
            row = c.execute(
                select(UsersTable.c.points_earned, UsersTable.c.points_spent)
                .where(UsersTable.c.id == g.user["id"])
            ).mappings().first()
        earned = float(row["points_earned"])
        spent  = float(row["points_spent"])
        return jsonify(earned=earned, spent=spent, balance=earned - spent), 200
    
    @api.post("/points/spend")
    @login_required
    def spend_points():
        d = request.get_json(silent=True) or {}
        try:
            amt = round(float(d.get("amount", 0)), 2)
        except Exception:
            return jsonify(error="invalid amount"), 400
        if amt <= 0:
            return jsonify(error="amount must be > 0"), 400
        note = (d.get("note") or "").strip() or None

        with app.extensions["engine"].begin() as c:
            # current totals
            u = c.execute(
                select(UsersTable.c.points_earned, UsersTable.c.points_spent)
                .where(UsersTable.c.id == g.user["id"])
            ).mappings().first()
            earned = float(u["points_earned"]); spent = float(u["points_spent"])
            balance = earned - spent
            if amt > balance + 1e-6:
                return jsonify(error="insufficient balance", balance=balance), 400

            # ledger (optional table)
            if "PointsSpendLedger" in globals():
                c.execute(insert(PointsSpendLedger).values(
                    user_id=g.user["id"], amount=amt, note=note, created_at_utc=datetime.utcnow()
                ))

            # bump spent
            c.execute(
                update(UsersTable)
                .where(UsersTable.c.id == g.user["id"])
                .values(points_spent = UsersTable.c.points_spent + amt)
            )

            # fetch fresh
            row = c.execute(
                select(UsersTable.c.points_earned, UsersTable.c.points_spent)
                .where(UsersTable.c.id == g.user["id"])
            ).mappings().first()

        new_balance = float(row["points_earned"] - row["points_spent"])
        return jsonify(ok=True, spent=amt, balance=new_balance), 200


    @api.get("/analytics/points_by_category")
    @login_required
    def points_by_category():
        # Accept period from query; ignore anchor for end bound (always today local)
        period = (request.args.get("period") or "week").lower()
        tzname = g.user.get("timezone") or "UTC"
        end_d = today_local_date(tzname)

        if period == "month":
            # rolling 30-day window, anchored on *today local*
            start_d = end_d - timedelta(days=30)
        else:
            period = "week"
            start_d = end_d - timedelta(days=6)            # last 7 days

        with app.extensions["engine"].connect() as c:
            rows = c.execute(
                select(
                    CompletedHabitsTable.c.day_local,
                    CompletedHabitsTable.c.category_id,
                    func.sum(CompletedHabitsTable.c.points_awarded).label("pts")
                )
                .where(and_(
                    CompletedHabitsTable.c.user_id == g.user["id"],
                    CompletedHabitsTable.c.day_local >= start_d,
                    CompletedHabitsTable.c.day_local <= end_d
                ))
                .group_by(CompletedHabitsTable.c.day_local, CompletedHabitsTable.c.category_id)
            ).mappings().all()

            # Meta for categories in the window
            cat_ids = sorted({r["category_id"] for r in rows if r["category_id"] is not None})
            meta_map = {}
            if cat_ids:
                meta_rows = c.execute(
                    select(CategoriesTable.c.id, CategoriesTable.c.category_name, CategoriesTable.c.emoji, CategoriesTable.c.color)
                    .where(CategoriesTable.c.id.in_(cat_ids))
                ).mappings().all()
                for m in meta_rows:
                    meta_map[m["id"]] = {
                        "id": m["id"],
                        "name": m["category_name"],
                        "emoji": m["emoji"],
                        "color": m["color"] or "#E5E7EB",
                    }

        # Day -> {cat_id: pts_that_day}
        day_cat = {}
        for r in rows:
            d = r["day_local"]
            day_cat.setdefault(d, {})[r["category_id"]] = float(r["pts"])

        # Buckets (local days)
        all_days = list(date_range_inclusive(start_d, end_d))
        buckets = [d.isoformat() for d in all_days]

        # Category ordering
        cats = sorted(meta_map.keys())
        categories = [meta_map.get(cid, {"id": cid, "name": "Deleted", "emoji": "📁", "color": "#E5E7EB"}) for cid in cats]

        # Build cumulative series per category + total
        cum_by_cat = {cid: 0.0 for cid in cats}
        series = {str(cid): [] for cid in cats}
        total_series = []
        for d in all_days:
            per_day = day_cat.get(d, {})
            day_total = 0.0
            for cid in cats:
                inc = float(per_day.get(cid, 0.0))
                cum_by_cat[cid] += inc
                series[str(cid)].append(round(cum_by_cat[cid], 2))
                day_total += inc
            prev_total = total_series[-1] if total_series else 0.0
            total_series.append(round(prev_total + day_total, 2))

        return jsonify(
            period=period,                 # now correct
            start=start_d.isoformat(),
            end=end_d.isoformat(),         # ALWAYS today (user local)
            buckets=buckets,
            categories=categories,         # [{id,name,emoji,color}]
            series=series,                 # { "catId": [cum...] }
            total=total_series             # [cum...]
        ), 200

    @api.get("/analytics/points_over_time")
    @login_required
    def points_over_time():
        """
        Query params:
        scope=week|month  (default week)
        end=YYYY-MM-DD    (optional; default = today in user's TZ)
        Returns:
        { buckets: [{day:'YYYY-MM-DD', earned: x, spent: y, net: e-y, cum: CUM}], start, end }
        """
        period = (request.args.get("period") or request.args.get("scope") or "week").lower()

        tzname = g.user.get("timezone") or "UTC"
        try:
            tz = ZoneInfo(tzname)
        except Exception:
            tz = ZoneInfo("UTC")

        # end day in user's TZ (default = today)
        end_qs = request.args.get("end")
        if end_qs:
            try:
                end_local = datetime.strptime(end_qs, "%Y-%m-%d").date()
            except ValueError:
                return jsonify(error="invalid end"), 400
        else:
            end_local = datetime.now(tz).date()

        if period == "month":
            # last 30 days rolling (or change to calendar month if you prefer)
            start_local = end_local - timedelta(days=29)
        else:  # week
            start_local = end_local - timedelta(days=6)
            period = "week"

        # Build list of local days
        days = []
        d = start_local
        while d <= end_local:
            days.append(d)
            d += timedelta(days=1)

        # ---------- EARNED: already local ----------
        with app.extensions["engine"].connect() as c:
            earned_rows = c.execute(
                select(
                    CompletedHabitsTable.c.day_local.label("day"),
                    func.sum(CompletedHabitsTable.c.points_awarded).label("sum_pts")
                )
                .where(and_(
                    CompletedHabitsTable.c.user_id == g.user["id"],
                    CompletedHabitsTable.c.day_local >= start_local,
                    CompletedHabitsTable.c.day_local <= end_local,
                ))
                .group_by(CompletedHabitsTable.c.day_local)
            ).mappings().all()
            earned_map = { r["day"]: float(r["sum_pts"] or 0.0) for r in earned_rows }

            # ---------- SPENT: convert UTC → local day ----------
            spent_rows = c.execute(
                select(
                    RewardsPurchasedTable.c.purchased_at_utc.label("ts_utc"),
                    RewardsPurchasedTable.c.points_spent.label("spent")
                )
                .where(and_(
                    RewardsPurchasedTable.c.user_id == g.user["id"],
                    # fetch a little extra on both sides in case tz conversion crosses boundaries
                    RewardsPurchasedTable.c.purchased_at_utc >= datetime.combine(start_local, datetime.min.time()).replace(tzinfo=timezone.utc) - timedelta(hours=12),
                    RewardsPurchasedTable.c.purchased_at_utc <= datetime.combine(end_local, datetime.max.time()).replace(tzinfo=timezone.utc) + timedelta(hours=12),
                ))
            ).mappings().all()

        def utc_to_local_day(dt_utc):
            if dt_utc is None: return None
            # normalize to aware UTC
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            return dt_utc.astimezone(tz).date()

        spent_map = {}
        for r in spent_rows:
            local_day = utc_to_local_day(r["ts_utc"])
            if local_day is None: 
                continue
            if local_day < start_local or local_day > end_local:
                continue
            spent_map[local_day] = spent_map.get(local_day, 0.0) + float(r["spent"] or 0.0)

        # Build buckets & cumulative
        buckets = []
        running = 0.0
        for day in days:
            e = earned_map.get(day, 0.0)
            s = spent_map.get(day, 0.0)
            net = e - s
            running += net
            buckets.append({
                "day": day.isoformat(),
                "earned": round(e, 2),
                "spent": round(s, 2),
                "net": round(net, 2),
                "cum": round(running, 2),
            })

        return jsonify(
            scope=period,
            start=start_local.isoformat(),
            end=end_local.isoformat(),
            buckets=buckets,
        ), 200
    
    @api.get("/rewards")
    @login_required
    def list_rewards():
        creator = UsersTable.alias("creator_rewards")
        with app.extensions["engine"].connect() as c:
            # fetch rewards
            rows = c.execute(
                select(
                    RewardsTable.c.id.label("id"),
                    RewardsTable.c.name.label("name"),
                    RewardsTable.c.emoji.label("emoji"),
                    RewardsTable.c.color.label("color"),
                    RewardsTable.c.cost_points.label("cost_points"),
                    RewardsTable.c.is_recurring.label("is_recurring"),
                    RewardsTable.c.active.label("active"),
                    RewardsTable.c.created_at_utc.label("created_at_utc"),
                    creator.c.username.label("creator_username"),
                    creator.c.emoji.label("creator_emoji"),
                    creator.c.accent_color.label("creator_color"),
                )
                .select_from(
                    RewardsTable.outerjoin(creator, RewardsTable.c.creator_user_id == creator.c.id)
                )
                .where(and_(
                    RewardsTable.c.user_id == g.user["id"],
                    RewardsTable.c.active == 1
                ))
                .order_by(RewardsTable.c.created_at_utc.desc())
            ).mappings().all()

            # fetch balance
            u = c.execute(
                select(
                    UsersTable.c.points_earned.label("earned"),
                    UsersTable.c.points_spent.label("spent"),
                ).where(UsersTable.c.id == g.user["id"])
            ).mappings().first()
            balance = float((u["earned"] or 0) - (u["spent"] or 0))

        rewards = [{
            "id": r["id"],
            "name": r["name"],
            "emoji": r["emoji"] or "🎁",
            "color": r["color"] or "#E5E7EB",
            "cost_points": float(r["cost_points"]),
            "is_recurring": bool(r["is_recurring"]),
            "active": bool(r["active"]),
            "created_at_utc": r["created_at_utc"].isoformat() if r["created_at_utc"] else None,
            "creator_username": r.get("creator_username"),
            "creator_emoji": r.get("creator_emoji"),
            "creator_color": r.get("creator_color"),
        } for r in rows]

        return jsonify(rewards=rewards, balance=balance), 200


    @api.post("/rewards")
    @login_required
    def create_reward():
        data = request.get_json(force=True)
        name = (data.get("name") or "").strip()
        cost = data.get("cost_points")
        if not name or cost is None:
            return jsonify(error="name and cost_points required"), 400
        with app.extensions["engine"].begin() as c:
            c.execute(insert(RewardsTable).values(
                user_id=g.user["id"],
                name=name,
                emoji=data.get("emoji") or "🎁",
                color=data.get("color") or "#E5E7EB",
                cost_points=cost,
                is_recurring=1 if data.get("is_recurring") else 0,
            ))
        return jsonify(ok=True), 200

    @api.put("/rewards/<int:rid>")
    @login_required
    def update_reward(rid):
        data = request.get_json(force=True)
        allowed = {k: v for k, v in {
            "name": data.get("name"),
            "emoji": data.get("emoji"),
            "color": data.get("color"),
            "cost_points": data.get("cost_points"),
            "is_recurring": 1 if data.get("is_recurring") else 0 if data.get("is_recurring") is not None else None,
        }.items() if v is not None}
        if not allowed:
            return jsonify(error="no fields to update"), 400
        with app.extensions["engine"].begin() as c:
            res = c.execute(
                update(RewardsTable)
                .where(and_(RewardsTable.c.id == rid, RewardsTable.c.user_id == g.user["id"], RewardsTable.c.active == 1))
                .values(**allowed)
            )
            if res.rowcount == 0:
                return jsonify(error="not found"), 404
        return jsonify(ok=True), 200

    @api.delete("/rewards/<int:rid>")
    @login_required
    def delete_reward(rid):
        with app.extensions["engine"].begin() as c:
            res = c.execute(
                update(RewardsTable)
                .where(and_(RewardsTable.c.id == rid, RewardsTable.c.user_id == g.user["id"], RewardsTable.c.active == 1))
                .values(active=0)
            )
            if res.rowcount == 0:
                return jsonify(error="not found"), 404
        return jsonify(ok=True), 200


    @api.post("/rewards/<int:rid>/purchase")
    @login_required
    def purchase_reward(rid):
        data = request.get_json(silent=True) or {}

        with app.extensions["engine"].begin() as c:
            # 1) fetch reward info (explicit labels)
            r = c.execute(
                select(
                    RewardsTable.c.id.label("id"),
                    RewardsTable.c.user_id.label("user_id"),
                    RewardsTable.c.cost_points.label("cost"),     # reward price lives here
                    RewardsTable.c.is_recurring.label("is_recurring"),
                    RewardsTable.c.active.label("active"),
                ).where(and_(
                    RewardsTable.c.id == rid,
                    RewardsTable.c.user_id == g.user["id"],
                    RewardsTable.c.active == 1,
                ))
            ).mappings().first()
            if not r:
                return jsonify(error="reward not found"), 404

            cost = float(r["cost"])

            # 2) current balance from UsersTable (points_earned / points_spent)
            ub = c.execute(
                select(
                    UsersTable.c.points_earned.label("earned"),
                    UsersTable.c.points_spent.label("spent"),
                ).where(UsersTable.c.id == g.user["id"])
            ).mappings().first()

            earned = float(ub["earned"] or 0)
            spent  = float(ub["spent"] or 0)
            balance = earned - spent
            if balance + 1e-9 < cost:
                return jsonify(error="insufficient points"), 400

            now = datetime.utcnow()

            # 3) record purchase into rewards_purchased
            # IMPORTANT: column name here must match your schema. Use points_spent (NOT cost_points).
            c.execute(
                insert(RewardsPurchasedTable).values(
                    user_id=g.user["id"],
                    reward_id=r["id"],
                    points_spent=cost,                 # <— FIXED NAME
                    purchased_at_utc=now,
                    note=data.get("note")  # only if you added this column
                )
            )

            # 4) spend ledger + bump user's points_spent
            c.execute(
                insert(PointsSpendLedger).values(   # <— use your actual model var name
                    user_id=g.user["id"],
                    amount=cost,
                    created_at_utc=now,
                )
            )

            c.execute(
                update(UsersTable)
                .where(UsersTable.c.id == g.user["id"])
                .values(points_spent=UsersTable.c.points_spent + cost)
            )

            # 5) deactivate one-time rewards
            if not bool(r["is_recurring"]):
                c.execute(
                    update(RewardsTable)
                    .where(RewardsTable.c.id == r["id"])
                    .values(active=0)
                )

            # 6) new balance
            nb = c.execute(
                select(
                    UsersTable.c.points_earned.label("earned"),
                    UsersTable.c.points_spent.label("spent"),
                ).where(UsersTable.c.id == g.user["id"])
            ).mappings().first()
            new_balance = float((nb["earned"] or 0) - (nb["spent"] or 0))

        return jsonify(ok=True, balance=new_balance), 200


    @api.get("/rewards/purchases")
    @login_required
    def list_purchases():
        tzname = g.user.get("timezone") or "UTC"
        try:
            tz = ZoneInfo(tzname)
        except Exception:
            tz = ZoneInfo("UTC")

        with app.extensions["engine"].connect() as c:
            rows = c.execute(
                select(
                    RewardsPurchasedTable.c.id.label("id"),
                    RewardsPurchasedTable.c.reward_id.label("reward_id"),
                    RewardsPurchasedTable.c.points_spent.label("points_spent"),
                    RewardsPurchasedTable.c.purchased_at_utc.label("purchased_at_utc"),
                    RewardsTable.c.name.label("name"),
                    RewardsTable.c.emoji.label("emoji"),
                    RewardsTable.c.color.label("color"),
                )
                .select_from(
                    RewardsPurchasedTable.outerjoin(
                        RewardsTable, RewardsPurchasedTable.c.reward_id == RewardsTable.c.id
                    )
                )
                .where(RewardsPurchasedTable.c.user_id == g.user["id"])
                .order_by(RewardsPurchasedTable.c.purchased_at_utc.desc())
            ).mappings().all()

        def to_local(dt_utc):
            # stored as UTC (naive or aware) -> make sure it's UTC-aware, then convert
            if dt_utc is None:
                return None
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            return dt_utc.astimezone(tz)

        purchases = [{
            "id": r["id"],
            "reward_id": r["reward_id"],
            "name": r["name"] or "Reward",
            "emoji": r["emoji"] or "🎁",
            "color": r["color"] or "#E5E7EB",
            "points_spent": float(r["points_spent"]),
            "purchased_at_utc": r["purchased_at_utc"].isoformat() if r["purchased_at_utc"] else None,
            "purchased_at_local": to_local(r["purchased_at_utc"]).isoformat() if r["purchased_at_utc"] else None,
        } for r in rows]

        return jsonify(purchases=purchases), 200
    

    @api.get("/ai/gratitude_cloud")
    @login_required
    def get_gratitude_cloud():
        """
        Returns the most recent cloud for the current user:
        { period_start, period_end, generated_at_utc, cloud: [{word,count}, ...] }
        """
        with app.extensions["engine"].connect() as c:
            row = c.execute(
                select(
                    AiProcessedGratitudesTable.c.period_start,
                    AiProcessedGratitudesTable.c.period_end,
                    AiProcessedGratitudesTable.c.generated_at_utc,
                    AiProcessedGratitudesTable.c.cloud
                )
                .where(AiProcessedGratitudesTable.c.user_id == g.user["id"])
                .order_by(AiProcessedGratitudesTable.c.generated_at_utc.desc())
                .limit(1)
            ).mappings().first()

        if not row:
            return jsonify(available=False, message="No gratitude cloud yet."), 200

        return jsonify(
            available=True,
            period_start=row["period_start"].isoformat(),
            period_end=row["period_end"].isoformat(),
            generated_at_utc=row["generated_at_utc"].isoformat(),
            cloud=row["cloud"],
        ), 200
    
    @api.get("/ai/motivation")
    @login_required
    def get_motivation():
        with app.extensions["engine"].connect() as c:
            row = c.execute(
                select(AiGeneratedMotivationsTable.c.text,
                    AiGeneratedMotivationsTable.c.generated_at_utc)
                .where(AiGeneratedMotivationsTable.c.user_id == g.user["id"])
                .order_by(AiGeneratedMotivationsTable.c.generated_at_utc.desc())
                .limit(1)
            ).mappings().first()

        if not row:
            return jsonify(available=False), 200

        return jsonify(
            available=True,
            text=row["text"],
            generated_at=row["generated_at_utc"].isoformat() + "Z"
        ), 200

    @api.post("/ai/motivation/refresh")
    @login_required
    def refresh_motivation():
        now = datetime.now(timezone.utc).replace(tzinfo=None)  # store naive UTC in DB for consistency with others
        with app.extensions["engine"].begin() as c:
            last = c.execute(
                select(AiGeneratedMotivationsTable.c.generated_at_utc)
                .where(AiGeneratedMotivationsTable.c.user_id == g.user["id"])
                .order_by(AiGeneratedMotivationsTable.c.generated_at_utc.desc())
                .limit(1)
            ).scalar()

            if last:
                delta = now - last
                if delta < MOTIVATION_MIN_INTERVAL:
                    retry_at = last + MOTIVATION_MIN_INTERVAL
                    retry_sec = int((retry_at - now).total_seconds())
                    return jsonify(
                        error=f"Try again at in {(retry_sec // 60)} mins",
                        retry_seconds=max(1, retry_sec),
                        retry_at=retry_at.isoformat() + "Z"
                    ), 429

            # Generate new text via OpenAI
            text = generate_motivation(c, g.user["id"])

            c.execute(
                insert(AiGeneratedMotivationsTable).values(
                    user_id=g.user["id"],
                    text=text,
                    source="on_demand",
                    model=OPENAI_MODEL,
                    prompt_version=PROMPT_VERSION,
                    generated_at_utc=now,
                )
            )

        return jsonify(ok=True, text=text, generated_at=now.isoformat() + "Z"), 200
    
    @api.get("/track/completed")
    @login_required
    def api_track_completed():
        def parse_iso(ts):
            if not ts: return None
            try:
                if len(ts) == 10:  # YYYY-MM-DD
                    return datetime.fromisoformat(ts + "T00:00:00")
                return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                return None

        since = parse_iso(request.args.get("since"))
        until = parse_iso(request.args.get("until"))
        try:    limit  = max(1, min(500, int(request.args.get("limit", "200"))))
        except: limit  = 200
        try:    offset = max(0, int(request.args.get("offset", "0")))
        except: offset = 0

        u = g.user["id"]

        conds = [CompletedHabitsTable.c.user_id == u]
        if since: conds.append(CompletedHabitsTable.c.completed_at_local >= since)
        if until: conds.append(CompletedHabitsTable.c.completed_at_local <= until)

        # LEFT JOIN categories (same user)
        stmt = (
            select(
                CompletedHabitsTable.c.id,
                CompletedHabitsTable.c.habit_id,
                CompletedHabitsTable.c.category_id,
                CompletedHabitsTable.c.name_snapshot,
                CompletedHabitsTable.c.points_mode,
                CompletedHabitsTable.c.challenge,
                CompletedHabitsTable.c.importance,
                CompletedHabitsTable.c.base_value,
                CompletedHabitsTable.c.time_minutes,
                CompletedHabitsTable.c.percent_value,
                CompletedHabitsTable.c.points_awarded,
                CompletedHabitsTable.c.completed_at_local,
                CompletedHabitsTable.c.day_local,
                CompletedHabitsTable.c.created_at_utc,
                CategoriesTable.c.category_name.label("category_name"),
                CategoriesTable.c.emoji.label("category_emoji"),
                CategoriesTable.c.color.label("category_color"),
            )
            .select_from(
                CompletedHabitsTable.outerjoin(
                    CategoriesTable,
                    and_(
                        CategoriesTable.c.id == CompletedHabitsTable.c.category_id,
                        CategoriesTable.c.user_id == u,
                    )
                )
            )
            .where(and_(*conds))
            .order_by(CompletedHabitsTable.c.completed_at_local.desc())
            .limit(limit)
            .offset(offset)
        )

        with app.extensions["engine"].connect() as c:
            rows = c.execute(stmt).mappings().all()

        items = []
        for r in rows:
            items.append({
                "id": r["id"],
                "habit_id": r["habit_id"],
                "category_id": r["category_id"],
                "name_snapshot": r["name_snapshot"],
                "points_mode": r["points_mode"],
                "challenge": r["challenge"],
                "importance": r["importance"],
                "base_value": float(r["base_value"]) if r["base_value"] is not None else None,
                "time_minutes": r["time_minutes"],
                "percent_value": float(r["percent_value"]) if r["percent_value"] is not None else None,
                "points_awarded": float(r["points_awarded"]) if r["points_awarded"] is not None else 0.0,
                "completed_at_local": r["completed_at_local"].isoformat() if r["completed_at_local"] else None,
                "day_local": r["day_local"].isoformat() if r["day_local"] else None,
                "created_at_utc": r["created_at_utc"].isoformat() + "Z" if r["created_at_utc"] else None,

                # category extras
                "category_name": r["category_name"],
                "category_emoji": r["category_emoji"],
                "category_color": r["category_color"],

                # convenient aliases
                "name": r["name_snapshot"],
                "points": float(r["points_awarded"]) if r["points_awarded"] is not None else 0.0,
            })

        return jsonify({"items": items}), 200
    
    @api.post("/habits/ai/preview")
    @login_required
    def api_ai_habit_preview():
        payload = request.get_json(silent=True) or {}
        category_id = payload.get("category_id")
        user_input  = (payload.get("user_input") or "").strip()

        # soft validation
        if user_input and len(user_input) > 280:
            return jsonify(error="user_input too long (max 280 chars)"), 400
        if category_id is not None and not isinstance(category_id, int):
            return jsonify(error="category_id must be an integer"), 400

        now = _now_utc().replace(tzinfo=None)
        u = g.user["id"]

        with app.extensions["engine"].begin() as c:
            # rate limit by last ai-created habit
            last = c.execute(
                select(func.max(HabitsTable.c.created_at_utc))
                .where(and_(
                    HabitsTable.c.user_id == u,
                    HabitsTable.c.ai_created == True
                ))
            ).scalar()

            if last:
                delta = now - last
                if delta < AI_HABIT_MIN_INTERVAL:
                    retry_at = last + AI_HABIT_MIN_INTERVAL
                    retry_sec = max(1, int((retry_at - now).total_seconds()))
                    return jsonify(
                        error=f"Too soon; try again in {retry_sec//60} mins",
                        retry_seconds=retry_sec,
                        retry_at=retry_at.isoformat() + "Z"
                    ), 429

            # optional: verify category belongs to user
            if category_id is not None:
                exists = c.execute(
                    select(CategoriesTable.c.id)
                    .where(and_(CategoriesTable.c.id == category_id, CategoriesTable.c.user_id == u))
                    .limit(1)
                ).scalar()
                if not exists:
                    return jsonify(error="category not found"), 404

            try:
                tzname = g.user.get("timezone") or "UTC"
                today_date = today_local_date(tzname)
                proposal = generate_habit(c, u, category_id, user_input, today_date)
            except Exception as e:
                print(f'ERROR: got exception {e}')
                return jsonify(error="AI could not generate a habit right now"), 502

        # NOTE: not saved; caller must confirm via POST /api/habits
        return jsonify(ok=True, proposal=proposal, generated_at=now.isoformat()+"Z"), 200
    
    @api.get("/focus")
    @login_required
    def api_focus():
        with app.extensions["engine"].connect() as c:
            row = c.execute(
                select(CategoriesTable.c.id, CategoriesTable.c.category_name,
                    CategoriesTable.c.emoji, CategoriesTable.c.color,
                    CategoriesTable.c.ai_summary, CategoriesTable.c.is_focused)
                .where(and_(CategoriesTable.c.user_id == g.user["id"], CategoriesTable.c.is_focused == True))
                .limit(1)
            ).mappings().first()
        if not row:
            return jsonify(available=False), 200
        return jsonify(
            available=True,
            category=dict(
                id=row["id"],
                name=row["category_name"],
                emoji=row["emoji"],
                color=row["color"],
                is_focused=bool(row["is_focused"]),
            ),
            blurb=row["ai_summary"],
            multiplier=FOCUS_CAT_MULTIPLIER,
        ), 200

    @api.put("/habits/<int:hid>")
    @login_required
    def update_habit(hid):
        d = request.get_json(silent=True) or {}
        now = datetime.utcnow()

        with app.extensions["engine"].begin() as c:
            # Ensure habit belongs to user
            row = c.execute(
                select(HabitsTable.c.id, HabitsTable.c.user_id)
                .where(HabitsTable.c.id == hid)
            ).mappings().first()
            if not row or row["user_id"] != g.user["id"]:
                return jsonify(error="habit not found"), 404

            # Disallow edits if the habit is NOT recurring and has *any* completion rows
            if row.get("type", "one-off") == "recurring":
                done = c.execute(
                    select(func.count(CompletedHabitsTable.c.id))
                    .where(CompletedHabitsTable.c.habit_id == hid)
                ).scalar() or 0
                if done > 0:
                    return jsonify(error="cannot edit a completed habit"), 400

            # Accept the same fields as create (subset allowed)
            fields = {
                "name": d.get("name"),
                "category_id": d.get("category_id"),
                "type": d.get("type"),
                "date_local": d.get("date_local"),
                "challenge": d.get("challenge"),
                "importance": d.get("importance"),
                "base_value": d.get("base_value"),
                "time_minutes": d.get("time_minutes"),
                "percent_target": d.get("percent_target"),
                "instances": d.get("instances")
            }
            # Drop Nones so we only update what's provided
            payload = {k:v for k,v in fields.items() if v is not None}
            if not payload:
                return jsonify(error="no fields to update"), 400

            # Basic validations mirroring create
            if "type" in payload and payload["type"] not in ("one-off","recurring"):
                return jsonify(error="invalid type"), 400
            if "challenge" in payload and payload["challenge"] not in ("automatic","easy","difficult","hard","daunting"):
                return jsonify(error="invalid challenge"), 400
            if "importance" in payload and int(payload["importance"]) not in (1,2,3):
                return jsonify(error="invalid importance"), 400
            
            if "instances" in payload:
                try:
                    instances = int(payload["instances"])
                except ValueError:
                    return jsonify(error="instances must be an integer"), 400
                if instances < 1 or instances > 10:
                    return jsonify(error="instances must be between 1 and 10"), 400
                payload["instances"] = instances
            
            schedule = None
            if payload.get("type", "") == "recurring":
                try:
                    schedule = _normalize_schedule(d.get("schedule"))
                except ValueError as e:
                    schedule = FULL_SCHEDULE
            payload["schedule"] = schedule

            payload["updated_at_utc"] = now
            c.execute(update(HabitsTable).where(HabitsTable.c.id == hid).values(**payload))

            full = c.execute(select(HabitsTable).where(HabitsTable.c.id == hid)).mappings().first()
            return jsonify(id=full["id"], name=full["name"], type=full["type"], date_local=full["date_local"]), 200
        
    @api.get("/calendar/progress")
    @login_required
    def calendar_progress():
        uid = g.user["id"]
        tzname = g.user.get("timezone") or "UTC"

        try:
            year  = int(request.args.get("year"))
            month = int(request.args.get("month"))
        except:
            return jsonify(error="year & month required"), 400

        days_in_month = monthrange(year, month)[1]
        month_start = date(year, month, 1)
        month_end   = date(year, month, days_in_month)

        # storage by day
        earned = { }
        avail  = { }

        with app.extensions["engine"].connect() as c:

            # ✅ COMPLETED POINTS (same as /habits)
            for d_local, pts in c.execute(
                select(
                    CompletedHabitsTable.c.day_local,
                    func.sum(CompletedHabitsTable.c.points_awarded)
                )
                .where(and_(
                    CompletedHabitsTable.c.user_id == uid,
                    CompletedHabitsTable.c.day_local >= month_start,
                    CompletedHabitsTable.c.day_local <= month_end,
                ))
                .group_by(CompletedHabitsTable.c.day_local)
            ):
                earned[d_local] = float(pts or 0)

            # ✅ FETCH ALL ACTIVE HABITS + CATEGORY METADATA
            rows = c.execute(
                select(
                    HabitsTable.c.id,
                    HabitsTable.c.name,
                    HabitsTable.c.type,
                    HabitsTable.c.date_local,
                    HabitsTable.c.base_value,
                    HabitsTable.c.challenge,
                    HabitsTable.c.importance,
                    HabitsTable.c.time_minutes,
                    HabitsTable.c.percent_target,
                    HabitsTable.c.created_at_utc,
                    HabitsTable.c.schedule,          # 👈 needed for habit_active_on_day
                    HabitsTable.c.active,
                    CategoriesTable.c.points_mode,
                    CategoriesTable.c.is_focused,
                )
                .join(CategoriesTable,
                    HabitsTable.c.category_id == CategoriesTable.c.id)
                .where(and_(
                    HabitsTable.c.user_id == uid,
                    HabitsTable.c.active == 1,
                ))
            ).mappings().all()


        def add_avail(day, pts):
            if pts and pts > 0:
                avail[day] = avail.get(day, 0) + float(pts)

        # ✅ POTENTIAL POINTS ACCURATELY REBUILT FOR EACH DAY
        for r in rows:
            for d in range(1, days_in_month + 1):
                day_obj = date(year, month, d)
                pts = _points_available_for_habit_on_day(r, day_obj, tzname)
                if pts > 0:
                    add_avail(day_obj, pts)
        
        # ✅ Final MONTH list
        days = []
        for d in range(1, days_in_month + 1):
            iso = date(year, month, d)
            e = earned.get(iso, 0)
            a = avail.get(iso, 0)
            pct = round(e / a, 4) if a > 0 else None
            days.append({
                "date": iso.isoformat(),
                "percent": pct
            })

        # ✅ WEEK STRIP (last 7 LOCAL days)
        today = today_local_date(tzname)
        dow = today.weekday()           # Mon=0..Sun=6
        sunday_offset = (dow + 1) % 7   # Sun=0
        week_start = today - timedelta(days=sunday_offset)

        week = []
        for i in range(7):
            d = week_start + timedelta(days=i)
            if month_start <= d <= month_end:
                e = earned.get(d, 0)
                a = avail.get(d, 0)
                pct = round(e / a, 4) if a > 0 else None
            else:
                pct = None
            week.append({
                "date": d.isoformat(),
                "percent": pct
            })

        return jsonify({
            "year": year,
            "month": month,
            "days": days,
            "week": week,  # ✅ added back for CalendarWidget week view
        }), 200
    

    # ----------- SOCIAL STUFF ----------- #

    @api.get("/users/search")
    @login_required
    def search_users():
        q = (request.args.get("q") or "").strip()
        if not q:
            return jsonify(users=[])

        me_id = g.user["id"]
        like = f"%{q}%"

        engine = app.extensions["engine"]
        with engine.connect() as conn:
            # adjust to whatever your display-name field is
            user_rows = conn.execute(
                select(
                    UsersTable.c.id,
                    UsersTable.c.username,
                    UsersTable.c.emoji,
                    UsersTable.c.accent_color,
                )
                .where(
                    UsersTable.c.username.ilike(like),
                    UsersTable.c.id != me_id,
                )
                .limit(25)
            ).mappings().all()

            if not user_rows:
                return jsonify(users=[])

            target_ids = [r["id"] for r in user_rows]

            fr_rows = conn.execute(
                select(FriendsTable)
                .where(
                    and_(
                        FriendsTable.c.status.in_(["pending", "accepted"]),
                        or_(
                            and_(
                                FriendsTable.c.friending_user_id == me_id,
                                FriendsTable.c.friended_user_id.in_(target_ids),
                            ),
                            and_(
                                FriendsTable.c.friended_user_id == me_id,
                                FriendsTable.c.friending_user_id.in_(target_ids),
                            ),
                        ),
                    )
                )
            ).mappings().all()

            friendship_by_other = {}
            for fr in fr_rows:
                # identify the other user in this pair
                if fr["friending_user_id"] == me_id:
                    other_id = fr["friended_user_id"]
                else:
                    other_id = fr["friending_user_id"]
                friendship_by_other[other_id] = _friendship_to_dict(fr, me_id)

            result = []
            for u in user_rows:
                result.append(
                    {
                        "id": u["id"],
                        "name": u["username"],
                        "emoji": u["emoji"],
                        "color": u["accent_color"],
                        "friendship": friendship_by_other.get(u["id"]),
                    }
                )

            return jsonify(users=result)

    @api.get("/friends")
    @login_required
    def list_friendships():
        me_id = g.user["id"]
        status = request.args.get("status")

        engine = app.extensions["engine"]
        with engine.connect() as conn:
            where_clause = or_(
                FriendsTable.c.friending_user_id == me_id,
                FriendsTable.c.friended_user_id == me_id,
            )
            if status:
                where_clause = and_(where_clause, FriendsTable.c.status == status)

            rows = conn.execute(
                select(FriendsTable).where(where_clause)
            ).mappings().all()

            # build base friendships
            friendships = [_friendship_to_dict(r, me_id) for r in rows]

            # collect other_user_ids
            other_ids = {fr["other_user_id"] for fr in friendships}
            if other_ids:
                user_rows = conn.execute(
                    select(
                        UsersTable.c.id,
                        UsersTable.c.username,
                        UsersTable.c.emoji,
                        UsersTable.c.accent_color,
                    ).where(UsersTable.c.id.in_(other_ids))
                ).mappings().all()
                users_by_id = {
                    u["id"]: {
                        "id": u["id"],
                        "name": u["username"],
                        "emoji": u["emoji"],
                        "color": u["accent_color"],
                    }
                    for u in user_rows
                }
            else:
                users_by_id = {}

            # attach other_user block
            for fr in friendships:
                fr["other_user"] = users_by_id.get(fr["other_user_id"])

            return jsonify(friendships=friendships)

        
    @api.post("/friends")
    @login_required
    def create_friend_request():
        data = request.get_json() or {}
        me_id = g.user["id"]
        target_id = data.get("user_id") or data.get("friended_user_id")
        message = (data.get("message") or "").strip() or None

        if not target_id:
            return jsonify(error="missing user_id"), 400
        if target_id == me_id:
            return jsonify(error="cannot friend yourself"), 400

        now = datetime.now(timezone.utc)

        engine = app.extensions["engine"]
        with engine.begin() as conn:
            # Check existing friendship in either direction
            existing = conn.execute(
                select(FriendsTable)
                .where(
                    or_(
                        and_(
                            FriendsTable.c.friending_user_id == me_id,
                            FriendsTable.c.friended_user_id == target_id,
                        ),
                        and_(
                            FriendsTable.c.friending_user_id == target_id,
                            FriendsTable.c.friended_user_id == me_id,
                        ),
                    )
                )
            ).mappings().first()

            if existing and existing["status"] in ("pending", "accepted"):
                return jsonify(
                    error="friendship or request already exists",
                    friendship=_friendship_to_dict(existing, me_id),
                ), 409

            elif existing:
                result = conn.execute(
                    update(FriendsTable)
                    .where(
                        and_(
                            FriendsTable.c.friending_user_id == me_id,
                            FriendsTable.c.friended_user_id == target_id,
                        )
                    )
                    .values(
                        status="pending",
                        message=message,
                        updated_at_utc=now,
                    )
                )
                friendship_id = existing.friendship_id
            else:
                result = conn.execute(
                    insert(FriendsTable).values(
                        friending_user_id=me_id,
                        friended_user_id=target_id,
                        status="pending",
                        message=message,
                        created_at_utc=now,
                        updated_at_utc=now,
                    )
                )
                friendship_id = result.inserted_primary_key[0]

            row = conn.execute(
                select(FriendsTable).where(
                    FriendsTable.c.friendship_id == friendship_id
                )
            ).mappings().first()

        return jsonify(friendship=_friendship_to_dict(row, me_id)), 201
    
    @api.patch("/friends/<int:friendship_id>")
    @login_required
    def update_friendship(friendship_id):
        data = request.get_json() or {}
        new_status = data.get("status")
        if new_status not in ("accepted", "rejected"):
            return jsonify(error="invalid status"), 400

        me_id = g.user["id"]
        now = datetime.now(timezone.utc)

        engine = app.extensions["engine"]
        with engine.begin() as conn:
            row = conn.execute(
                select(FriendsTable)
                .where(FriendsTable.c.friendship_id == friendship_id)
            ).mappings().first()

            if not row:
                return jsonify(error="not found"), 404

            if me_id not in (
                row["friending_user_id"],
                row["friended_user_id"],
            ):
                return jsonify(error="forbidden"), 403

            # Only the *recipient* can accept/reject a pending request
            if row["status"] != "pending":
                return jsonify(error="cannot change non-pending friendship"), 400
            if me_id != row["friended_user_id"]:
                return jsonify(error="only recipient may accept/reject"), 403

            conn.execute(
                update(FriendsTable)
                .where(FriendsTable.c.friendship_id == friendship_id)
                .values(status=new_status, updated_at_utc=now)
            )

            updated = conn.execute(
                select(FriendsTable)
                .where(FriendsTable.c.friendship_id == friendship_id)
            ).mappings().first()

        return jsonify(friendship=_friendship_to_dict(updated, me_id))
    
    @api.delete("/friends/<int:friendship_id>")
    @login_required
    def delete_friendship(friendship_id):
        me_id = g.user["id"]

        engine = app.extensions["engine"]
        with engine.begin() as conn:
            row = conn.execute(
                select(FriendsTable)
                .where(FriendsTable.c.friendship_id == friendship_id)
            ).mappings().first()

            if not row:
                return jsonify(error="not found"), 404

            if me_id not in (
                row["friending_user_id"],
                row["friended_user_id"],
            ):
                return jsonify(error="forbidden"), 403

            conn.execute(
                delete(FriendsTable)
                .where(FriendsTable.c.friendship_id == friendship_id)
            )

        return jsonify(ok=True)

    @api.get("/friends/<int:friend_id>/categories")
    @login_required
    def friend_categories(friend_id):
        me_id = g.user["id"]
        engine = app.extensions["engine"]
        with engine.connect() as conn:
            if not _are_friends(conn, me_id, friend_id):
                return jsonify(error="not friends"), 403
            rows = conn.execute(
                select(
                    CategoriesTable.c.id,
                    CategoriesTable.c.category_name,
                    CategoriesTable.c.emoji,
                    CategoriesTable.c.color,
                    CategoriesTable.c.points_mode,
                    CategoriesTable.c.is_default,
                )
                .where(CategoriesTable.c.user_id == friend_id)
                .order_by(CategoriesTable.c.is_default.desc(), CategoriesTable.c.category_name.asc())
            ).mappings().all()
        return jsonify(categories=[dict(r) for r in rows]), 200

    # ---------- Pending actions (send habits/rewards to friends) ----------
    @api.get("/pending/actions")
    @login_required
    def list_pending_actions():
        direction = (request.args.get("direction") or "outbound").lower()
        item_type = request.args.get("type")
        if direction not in ("outbound", "inbound"):
            return jsonify(error="invalid direction"), 400
        if item_type and item_type not in ("habit", "reward"):
            return jsonify(error="invalid type"), 400

        me = g.user["id"]
        engine = app.extensions["engine"]
        items = []
        with engine.connect() as conn:
            if not item_type or item_type == "habit":
                stmt = _pending_select_with_category(PendingHabitsTable, include_category=True)
                if direction == "outbound":
                    stmt = stmt.where(PendingHabitsTable.c.creator_user_id == me)
                else:
                    stmt = stmt.where(PendingHabitsTable.c.user_id == me)
                rows = conn.execute(stmt).mappings().all()
                items.extend(_pending_row_to_dict(r, "habit") for r in rows)

            if not item_type or item_type == "reward":
                stmt = _pending_select_with_category(PendingRewardsTable, include_category=False)
                if direction == "outbound":
                    stmt = stmt.where(PendingRewardsTable.c.creator_user_id == me)
                else:
                    stmt = stmt.where(PendingRewardsTable.c.user_id == me)
                rows = conn.execute(stmt).mappings().all()
                items.extend(_pending_row_to_dict(r, "reward") for r in rows)

        # sort newest first
        items.sort(key=lambda x: x.get("created_at_utc") or "", reverse=True)
        return jsonify(pending=items), 200

    @api.post("/pending/actions")
    @login_required
    def create_pending_action():
        data = request.get_json(silent=True) or {}
        item_type = (data.get("type") or "").lower()
        if item_type not in ("habit", "reward"):
            return jsonify(error="type must be habit or reward"), 400

        recipient_id = data.get("recipient_user_id") or data.get("user_id")
        if not recipient_id:
            return jsonify(error="recipient_user_id required"), 400
        try:
            recipient_id = int(recipient_id)
        except Exception:
            return jsonify(error="recipient_user_id invalid"), 400

        me = g.user["id"]
        if recipient_id == me:
            return jsonify(error="cannot send to yourself"), 400

        engine = app.extensions["engine"]
        with engine.begin() as conn:
            if not _are_friends(conn, me, recipient_id):
                return jsonify(error="not friends with recipient"), 403

            if item_type == "habit":
                try:
                    payload = _shape_pending_habit_payload(data, recipient_id, me, conn)
                except ValueError as e:
                    return jsonify(error=str(e)), 400
                res = conn.execute(insert(PendingHabitsTable).values(**payload))
                pid = res.inserted_primary_key[0]
                row = conn.execute(
                    _pending_select_with_category(PendingHabitsTable, include_category=True).where(PendingHabitsTable.c.id == pid)
                ).mappings().first()
                pending = _pending_row_to_dict(row, "habit")
            else:
                try:
                    payload = _shape_pending_reward_payload(data, recipient_id, me)
                except ValueError as e:
                    return jsonify(error=str(e)), 400
                res = conn.execute(insert(PendingRewardsTable).values(**payload))
                pid = res.inserted_primary_key[0]
                row = conn.execute(
                    _pending_select(PendingRewardsTable).where(PendingRewardsTable.c.id == pid)
                ).mappings().first()
                pending = _pending_row_to_dict(row, "reward")

        return jsonify(pending=pending), 201

    @api.put("/pending/actions/<string:item_type>/<int:pending_id>")
    @login_required
    def update_pending_action(item_type, pending_id):
        item_type = item_type.lower()
        if item_type not in ("habit", "reward"):
            return jsonify(error="invalid type"), 400
        data = request.get_json(silent=True) or {}
        me = g.user["id"]

        engine = app.extensions["engine"]
        with engine.begin() as conn:
            table = PendingHabitsTable if item_type == "habit" else PendingRewardsTable
            existing = conn.execute(
                select(table).where(table.c.id == pending_id)
            ).mappings().first()
            if not existing:
                return jsonify(error="not found"), 404
            if existing["creator_user_id"] != me:
                return jsonify(error="forbidden"), 403

            merged = dict(existing)
            merged.update({k: v for k, v in data.items() if v is not None})
            merged["user_id"] = existing["user_id"]  # lock recipient
            merged["creator_user_id"] = me           # lock creator

            if item_type == "habit":
                try:
                    payload = _shape_pending_habit_payload(merged, existing["user_id"], me, conn)
                except ValueError as e:
                    return jsonify(error=str(e)), 400
                payload.pop("created_at_utc", None)
                payload["updated_at_utc"] = datetime.utcnow()
                conn.execute(
                    update(PendingHabitsTable)
                    .where(PendingHabitsTable.c.id == pending_id)
                    .values(**payload)
                )
                row = conn.execute(
                    _pending_select_with_category(PendingHabitsTable, include_category=True).where(PendingHabitsTable.c.id == pending_id)
                ).mappings().first()
                pending = _pending_row_to_dict(row, "habit")
            else:
                try:
                    payload = _shape_pending_reward_payload(merged, existing["user_id"], me)
                except ValueError as e:
                    return jsonify(error=str(e)), 400
                payload.pop("created_at_utc", None)
                conn.execute(
                    update(PendingRewardsTable)
                    .where(PendingRewardsTable.c.id == pending_id)
                    .values(**payload)
                )
                row = conn.execute(
                    _pending_select(PendingRewardsTable).where(PendingRewardsTable.c.id == pending_id)
                ).mappings().first()
                pending = _pending_row_to_dict(row, "reward")

        return jsonify(pending=pending), 200

    @api.post("/pending/actions/<string:item_type>/<int:pending_id>/respond")
    @login_required
    def respond_pending_action(item_type, pending_id):
        item_type = item_type.lower()
        if item_type not in ("habit", "reward"):
            return jsonify(error="invalid type"), 400

        body = request.get_json(silent=True) or {}
        action = (body.get("action") or "").lower()
        if action not in ("accept", "reject"):
            return jsonify(error="action must be accept or reject"), 400

        me = g.user["id"]
        now = datetime.utcnow()
        engine = app.extensions["engine"]
        with engine.begin() as conn:
            table = PendingHabitsTable if item_type == "habit" else PendingRewardsTable
            row = conn.execute(
                select(table).where(table.c.id == pending_id)
            ).mappings().first()
            if not row:
                return jsonify(error="not found"), 404
            if row["user_id"] != me:
                return jsonify(error="forbidden"), 403

            if action == "reject":
                conn.execute(delete(table).where(table.c.id == pending_id))
                return jsonify(ok=True, deleted=True), 200

            # accept → create real record then remove pending
            if item_type == "habit":
                # ensure category still exists
                try:
                    cat = _resolve_category_for_user(conn, me, row["category_id"])
                except ValueError as e:
                    return jsonify(error=str(e)), 400

                payload = {
                    "user_id": row["user_id"],
                    "creator_user_id": row.get("creator_user_id"),
                    "category_id": cat["id"],
                    "name": row["name"],
                    "type": row["type"],
                    "date_local": row["date_local"],
                    "challenge": row["challenge"],
                    "importance": row["importance"],
                    "base_value": row["base_value"],
                    "time_minutes": row["time_minutes"],
                    "percent_target": row["percent_target"],
                    "schedule": row["schedule"],
                    "notes": row["notes"],
                    "active": 1,
                    "ai_created": row.get("ai_created"),
                    "instances": row.get("instances") or 1,
                    "created_at_utc": now,
                    "updated_at_utc": now,
                }
                res = conn.execute(insert(HabitsTable).values(**payload))
                created_id = res.inserted_primary_key[0]
            else:
                payload = {
                    "user_id": row["user_id"],
                    "creator_user_id": row.get("creator_user_id"),
                    "name": row["name"],
                    "emoji": row["emoji"],
                    "color": row["color"],
                    "cost_points": row["cost_points"],
                    "is_recurring": row["is_recurring"],
                    "active": 1,
                    "created_at_utc": now,
                }
                res = conn.execute(insert(RewardsTable).values(**payload))
                created_id = res.inserted_primary_key[0]

            conn.execute(delete(table).where(table.c.id == pending_id))

        return jsonify(ok=True, created_type=item_type, created_id=created_id), 200


    @api.post("/users/summaries")
    @login_required
    def users_summaries():
        payload = request.get_json() or {}
        user_ids = payload.get("user_ids") or []
        try:
            user_ids = [int(u) for u in user_ids]
        except (TypeError, ValueError):
            return jsonify(error="user_ids must be a list of integers"), 400

        # unique + positive
        user_ids = list({u for u in user_ids if u > 0})
        if not user_ids:
            return jsonify(users=[]), 200

        engine = app.extensions["engine"]
        with engine.connect() as conn:
            # Basic user info (now includes ai_title)
            user_rows = conn.execute(
                select(
                    UsersTable.c.id,
                    UsersTable.c.username,
                    UsersTable.c.emoji,
                    UsersTable.c.accent_color,
                    UsersTable.c.ai_title,
                ).where(UsersTable.c.id.in_(user_ids))
            ).mappings().all()

            if not user_rows:
                return jsonify(users=[]), 200

            existing_ids = [r["id"] for r in user_rows]

            # For each user, aggregate points by category from last 50 completions
            per_user_points = {}   # uid -> {cat_id: points}
            per_user_samples = {}  # uid -> sample_size (<= 50)
            all_cat_ids = set()

            for uid in existing_ids:
                ch_rows = conn.execute(
                    select(
                        CompletedHabitsTable.c.category_id,
                        CompletedHabitsTable.c.points_awarded,
                    )
                    .where(CompletedHabitsTable.c.user_id == uid)
                    .order_by(CompletedHabitsTable.c.completed_at_local.desc())
                    .limit(50)
                ).mappings().all()

                per_user_samples[uid] = len(ch_rows)

                agg = defaultdict(int)
                for row in ch_rows:
                    cat_id = row["category_id"]
                    if cat_id is None:
                        continue
                    pts = row["points_awarded"] or 0
                    agg[cat_id] += int(pts)

                per_user_points[uid] = agg
                all_cat_ids.update(agg.keys())

            # Load category metadata
            categories_by_id = {}
            if all_cat_ids:
                cat_rows = conn.execute(
                    select(
                        CategoriesTable.c.id,
                        CategoriesTable.c.category_name,
                        CategoriesTable.c.emoji,
                        CategoriesTable.c.color,
                    ).where(CategoriesTable.c.id.in_(all_cat_ids))
                ).mappings().all()
                categories_by_id = {
                    c["id"]: {
                        "category_id": c["id"],
                        "name": c["category_name"],
                        "emoji": c["emoji"],
                        "color": c["color"],
                    }
                    for c in cat_rows
                }

            result = []
            for u in user_rows:
                uid = u["id"]
                agg = per_user_points.get(uid, {})
                sample_size = per_user_samples.get(uid, 0)

                # sort by points desc, then id, top 6
                top_pairs = sorted(
                    agg.items(),
                    key=lambda kv: (-kv[1], kv[0]),
                )[:6]

                top_categories = []
                for cat_id, pts in top_pairs:
                    meta = categories_by_id.get(cat_id)
                    if not meta:
                        continue
                    entry = dict(meta)
                    entry["points"] = int(pts)
                    top_categories.append(entry)

                total_points = sum(c["points"] for c in top_categories)

                # Backwards-compatible: keep `title` and `top_categories`
                # New: also expose ai_title / sample_size / total_points
                ai_title = u["ai_title"]
                title = ai_title or "Title coming soon"

                result.append(
                    {
                        "id": uid,
                        "username": u["username"],
                        "emoji": u["emoji"],
                        "accent_color": u["accent_color"],
                        "title": title,               # what your UI already uses
                        "top_categories": top_categories,  # what your UI already uses

                        # extra fields you *can* use later:
                        "ai_title": ai_title,
                        "sample_size": sample_size,
                        "total_points": total_points,
                    }
                )

            return jsonify(users=result), 200
        

    @api.post("/users/feed")
    @login_required
    def users_feed():
        """
        Unified feed for a set of users (completed habits, rewards, reflections).

        Request JSON:
        {
            "user_ids": [1, 2, 3],
            "offset": 0,
            "limit": 20
        }

        Response:
        {
            "items": [
                {
                    "feed_kind": "habit" | "reward" | "reflection",
                    "feed_item_id": int,
                    "user_id": int,
                    "username": str,
                    "emoji": str|null,
                    "accent_color": str|null,
                    "title": str,
                    "subtitle": str|null,
                    "points_delta": float|null,
                    "event_time": ISO8601 string,
                },
                ...
            ],
            "has_more": bool,
            "next_offset": int
        }
        """
        tzname = g.user.get("timezone") or "UTC"
        try:
            user_tz = ZoneInfo(tzname)
        except Exception:
            user_tz = ZoneInfo("UTC")

        payload = request.get_json() or {}
        user_ids = payload.get("user_ids") or []
        try:
            user_ids = [int(u) for u in user_ids]
        except (TypeError, ValueError):
            return jsonify(error="user_ids must be a list of integers"), 400

        # Deduplicate and filter
        user_ids = list({u for u in user_ids if u > 0})
        if not user_ids:
            return jsonify(items=[], has_more=False, next_offset=0), 200

        try:
            offset = int(payload.get("offset") or 0)
        except (TypeError, ValueError):
            offset = 0
        try:
            limit = int(payload.get("limit") or 20)
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(limit, 100))
        if offset < 0:
            offset = 0

        engine = app.extensions["engine"]
        with engine.connect() as conn:
            # IMPORTANT: all 3 SELECTs must have the same number of columns, in the same order.
            # Column order (index-based):
            #  0 feed_kind        ('habit' | 'reward' | 'reflection')
            #  1 feed_item_id     (id from completed_habits / rewards_purchased / reflections)
            #  2 user_id
            #  3 username
            #  4 emoji
            #  5 accent_color
            #  6 main_name        (habit_name / reward_name / reflection_summary)
            #  7 aux1             (category_name / reward_emoji / day_local)
            #  8 aux2             (category_emoji / NULL / NULL)
            #  9 points_delta     (+/- points or NULL)
            # 10 event_time       (datetime for sorting)

            # 1) Completed habits
            habits_q = (
                select(
                    literal("habit"),                          # 0 feed_kind
                    CompletedHabitsTable.c.id,                # 1 feed_item_id
                    CompletedHabitsTable.c.user_id,           # 2 user_id
                    UsersTable.c.username,                    # 3 username
                    UsersTable.c.emoji,                       # 4 emoji
                    CategoriesTable.c.color,                # 5 category color
                    CompletedHabitsTable.c.name_snapshot,     # 6 main_name
                    CategoriesTable.c.category_name,          # 7 aux1 (category name)
                    CategoriesTable.c.emoji,                  # 8 aux2 (category emoji)
                    CompletedHabitsTable.c.points_awarded,    # 9 points_delta
                    CompletedHabitsTable.c.created_at_utc, # 10 event_time
                    UsersTable.c.accent_color                # 11 user_color
                )
                .join(UsersTable, UsersTable.c.id == CompletedHabitsTable.c.user_id)
                .join(CategoriesTable, CategoriesTable.c.id == CompletedHabitsTable.c.category_id)
                .where(CompletedHabitsTable.c.user_id.in_(user_ids))
            )

            # 2) Rewards purchased
            rewards_q = (
                select(
                    literal("reward"),                         # 0 feed_kind
                    RewardsPurchasedTable.c.id,                # 1 feed_item_id
                    RewardsPurchasedTable.c.user_id,           # 2 user_id
                    UsersTable.c.username,                     # 3 username
                    UsersTable.c.emoji,                        # 4 emoji
                    UsersTable.c.accent_color,                 # 5 accent_color
                    RewardsTable.c.name,                       # 6 main_name (reward name)
                    RewardsTable.c.emoji,                      # 7 aux1 (reward emoji)
                    literal(None),                             # 8 aux2 (unused)
                    -RewardsPurchasedTable.c.points_spent,     # 9 points_delta (negative)
                    RewardsPurchasedTable.c.purchased_at_utc,   # 10 event_time
                    UsersTable.c.accent_color                # 11 user_color
                )
                .join(UsersTable, UsersTable.c.id == RewardsPurchasedTable.c.user_id)
                .outerjoin(RewardsTable, RewardsTable.c.id == RewardsPurchasedTable.c.reward_id)
                .where(RewardsPurchasedTable.c.user_id.in_(user_ids))
            )

            # 3) Reflections
            reflections_q = (
                select(
                    literal("reflection"),                     # 0 feed_kind
                    ReflectionsTable.c.id,                     # 1 feed_item_id
                    ReflectionsTable.c.user_id,                # 2 user_id
                    UsersTable.c.username,                     # 3 username
                    UsersTable.c.emoji,                        # 4 emoji
                    UsersTable.c.accent_color,                 # 5 accent_color
                    ReflectionsTable.c.summary,                # 6 main_name (summary)
                    ReflectionsTable.c.day_local,              # 7 aux1 (day_local)
                    literal(None),                             # 8 aux2 (unused)
                    literal(None),                             # 9 points_delta (none)
                    ReflectionsTable.c.created_at_utc,          # 10 event_time
                    UsersTable.c.accent_color                # 11 user_color
                )
                .join(UsersTable, UsersTable.c.id == ReflectionsTable.c.user_id)
                .where(ReflectionsTable.c.user_id.in_(user_ids))
            )

            # UNION ALL of the three
            union_stmt = habits_q.union_all(rewards_q, reflections_q)
            union_q = union_stmt.subquery("feed_items")

            # Column index 10 is the time column in all branches.
            time_col = list(union_q.c)[10]

            rows = (
                conn.execute(
                    select(union_q)
                    .order_by(time_col.desc())
                    .offset(offset)
                    .limit(limit + 1)   # fetch one extra to see if there's more
                )
                .all()
            )

            has_more = len(rows) > limit
            if has_more:
                rows = rows[:limit]

            items = []
            for row in rows:
                # row is a positional tuple; use indexes as documented above
                feed_kind = row[0]
                feed_item_id = row[1]
                user_id = row[2]
                username = row[3]
                emoji = row[4]
                accent_color = row[5]
                main_name = row[6]
                aux1 = row[7]
                aux2 = row[8]
                points_delta = row[9]
                raw_event_time = row[10]
                user_color = row[11]
                local_dt = _to_user_local(raw_event_time, user_tz)
                event_time_str = local_dt.isoformat() if local_dt is not None else None

                # Build title/subtitle based on kind
                if feed_kind == "habit":
                    title = f"Completed “{main_name}”"
                    subtitle_parts = []
                    if aux1:
                        subtitle_parts.append(aux1)  # category name
                    if points_delta is not None:
                        subtitle_parts.append(f"{int(points_delta)} pts")
                    subtitle = " · ".join(subtitle_parts) if subtitle_parts else None

                elif feed_kind == "reward":
                    reward_name = main_name or "Reward"
                    title = f"Purchased “{reward_name}”"
                    pts = points_delta or 0
                    subtitle = f"{int(abs(pts))} pts spent"

                else:  # reflection
                    title = "Daily reflection"
                    if hasattr(aux1, "isoformat"):
                        subtitle = aux1.isoformat()
                    else:
                        subtitle = None

                items.append(
                    {
                        "feed_kind": feed_kind,
                        "feed_item_id": feed_item_id,
                        "user_id": user_id,
                        "username": username,
                        "emoji": emoji,
                        "accent_color": accent_color,
                        "title": title,
                        "subtitle": subtitle,
                        "points_delta": float(points_delta) if points_delta is not None else None,
                        "event_time": event_time_str,
                        "user_color": user_color
                    }
                )

            next_offset = offset + len(items)

        return jsonify(items=items, has_more=has_more, next_offset=next_offset), 200


    
    @api.post("/feed/react")
    @login_required
    def feed_react():
        payload = request.get_json() or {}
        kind = (payload.get("feed_kind") or "").strip()
        try:
            item_id = int(payload.get("feed_item_id"))
        except (TypeError, ValueError):
            return jsonify(error="invalid feed_item_id"), 400

        reaction = (payload.get("reaction") or "").strip()
        user_id = g.user["id"]

        if kind not in ("habit", "reward", "reflection"):
            return jsonify(error="invalid feed_kind"), 400

        engine = app.extensions["engine"]
        with engine.begin() as conn:
            recipient_id = get_user_from_post(conn, kind, item_id)

            if not reaction:
                # delete existing
                conn.execute(
                    delete(FeedReactionsTable).where(
                        FeedReactionsTable.c.feed_kind == kind,
                        FeedReactionsTable.c.feed_item_id == item_id,
                        FeedReactionsTable.c.user_id == user_id,
                    )
                )
            else:
                # upsert
                existing_id = conn.execute(
                    select(FeedReactionsTable.c.id).where(
                        FeedReactionsTable.c.feed_kind == kind,
                        FeedReactionsTable.c.feed_item_id == item_id,
                        FeedReactionsTable.c.user_id == user_id,
                    )
                ).scalar_one_or_none()

                if existing_id is None:
                    conn.execute(
                        insert(FeedReactionsTable).values(
                            feed_kind=kind,
                            feed_item_id=item_id,
                            user_id=user_id,
                            recipient_id=recipient_id,
                            reaction=reaction,
                            created_at_utc=datetime.utcnow(),
                        )
                    )
                else:
                    conn.execute(
                        update(FeedReactionsTable)
                        .where(FeedReactionsTable.c.id == existing_id)
                        .values(
                            reaction=reaction,
                        )
                    )

            # recompute summary (top 5)
            rows = conn.execute(
                select(
                    FeedReactionsTable.c.reaction,
                    func.count().label("cnt"),
                )
                .where(
                    FeedReactionsTable.c.feed_kind == kind,
                    FeedReactionsTable.c.feed_item_id == item_id,
                )
                .group_by(FeedReactionsTable.c.reaction)
                .order_by(func.count().desc())
            ).all()

            my_row = conn.execute(
                select(FeedReactionsTable.c.reaction).where(
                    FeedReactionsTable.c.feed_kind == kind,
                    FeedReactionsTable.c.feed_item_id == item_id,
                    FeedReactionsTable.c.user_id == user_id,
                )
            ).scalar_one_or_none()

        reactions = [
            {"emoji": r[0], "count": int(r[1])}
            for r in rows[:5]
        ]

        return jsonify(
            feed_kind=kind,
            feed_item_id=item_id,
            my_reaction=my_row,
            reactions=reactions,
        ), 200
    
    @api.get("/feed/reactions")
    @login_required
    def get_feed_reactions():
        kind = (request.args.get("feed_kind") or "").strip()
        try:
            item_id = int(request.args.get("feed_item_id"))
        except (TypeError, ValueError):
            return jsonify(error="invalid feed_item_id"), 400

        if kind not in ("habit", "reward", "reflection"):
            return jsonify(error="invalid feed_kind"), 400

        user_id = g.user["id"]
        engine = app.extensions["engine"]
        with engine.connect() as conn:
            rows = conn.execute(
                select(
                    FeedReactionsTable.c.reaction,
                    func.count().label("cnt"),
                )
                .where(
                    FeedReactionsTable.c.feed_kind == kind,
                    FeedReactionsTable.c.feed_item_id == item_id,
                )
                .group_by(FeedReactionsTable.c.reaction)
                .order_by(func.count().desc())
            ).all()

            my_row = conn.execute(
                select(FeedReactionsTable.c.reaction).where(
                    FeedReactionsTable.c.feed_kind == kind,
                    FeedReactionsTable.c.feed_item_id == item_id,
                    FeedReactionsTable.c.user_id == user_id,
                )
            ).scalar_one_or_none()

        reactions = [
            {"emoji": r[0], "count": int(r[1])}
            for r in rows[:5]
        ]

        return jsonify(
            feed_kind=kind,
            feed_item_id=item_id,
            my_reaction=my_row,
            reactions=reactions,
        ), 200
    
    @api.get("/feed/comments")
    @login_required
    def get_feed_comments():
        kind = (request.args.get("feed_kind") or "").strip()
        try:
            item_id = int(request.args.get("feed_item_id"))
        except (TypeError, ValueError):
            return jsonify(error="invalid feed_item_id"), 400

        if kind not in ("habit", "reward", "reflection"):
            return jsonify(error="invalid feed_kind"), 400

        try:
            limit = int(request.args.get("limit") or 50)
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(limit, 200))

        # Figure out user's timezone
        tzname = g.user.get("timezone") or "UTC"
        try:
            user_tz = ZoneInfo(tzname)
        except Exception:
            user_tz = ZoneInfo("UTC")

        engine = app.extensions["engine"]
        with engine.connect() as conn:
            rows = (
                conn.execute(
                    select(
                        FeedCommentsTable.c.id,
                        FeedCommentsTable.c.user_id,
                        UsersTable.c.username,
                        FeedCommentsTable.c.comment_text,
                        FeedCommentsTable.c.created_at_utc,
                    )
                    .join(UsersTable, UsersTable.c.id == FeedCommentsTable.c.user_id)
                    .where(
                        FeedCommentsTable.c.feed_kind == kind,
                        FeedCommentsTable.c.feed_item_id == item_id,
                    )
                    .order_by(FeedCommentsTable.c.created_at_utc.asc())
                    .limit(limit)
                )
                .mappings()
                .all()
            )

        comments = []
        for r in rows:
            t = r["created_at_utc"]
            if t is not None:
                # Treat stored value as UTC, convert to user's timezone
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                else:
                    t = t.astimezone(timezone.utc)
                t_local = t.astimezone(user_tz)
                time_str = t_local.isoformat()
            else:
                time_str = None

            comments.append(
                {
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "username": r["username"],
                    "comment": r["comment_text"],
                    "time_local": time_str,   # 👈 renamed, but same position in shape
                }
            )

        return jsonify(
            feed_kind=kind,
            feed_item_id=item_id,
            comments=comments,
        ), 200

    @api.post("/feed/comments")
    @login_required
    def add_feed_comment():
        payload = request.get_json() or {}
        kind = (payload.get("feed_kind") or "").strip()
        try:
            item_id = int(payload.get("feed_item_id"))
        except (TypeError, ValueError):
            return jsonify(error="invalid feed_item_id"), 400

        comment_text = (payload.get("comment") or "").strip()
        if not comment_text:
            return jsonify(error="empty comment"), 400

        if kind not in ("habit", "reward", "reflection"):
            return jsonify(error="invalid feed_kind"), 400

        user_id = g.user["id"]
        tzname = g.user.get("timezone") or "UTC"
        try:
            user_tz = ZoneInfo(tzname)
        except Exception:
            user_tz = ZoneInfo("UTC")

        now_utc = datetime.now(timezone.utc)
        engine = app.extensions["engine"]
        with engine.begin() as conn:
            recipient_id = get_user_from_post(conn, kind, item_id)
            res = conn.execute(
                insert(FeedCommentsTable).values(
                    feed_kind=kind,
                    feed_item_id=item_id,
                    user_id=user_id,
                    recipient_id=recipient_id,
                    comment_text=comment_text,
                    created_at_utc=now_utc,          # stored as UTC
                )
            )
            comment_id = res.inserted_primary_key[0]

            username = conn.execute(
                select(UsersTable.c.username).where(UsersTable.c.id == user_id)
            ).scalar_one()

        # Convert to local for the response
        time_local = now_utc.astimezone(user_tz).isoformat()

        return jsonify(
            id=comment_id,
            feed_kind=kind,
            feed_item_id=item_id,
            user_id=user_id,
            username=username,
            comment=comment_text,
            time_utc=time_local,                   # UI keeps using .time_utc
        ), 200




    @api.get("/social/inbox")
    @login_required
    def get_inbox():
        user_id = g.user["id"]

        with app.extensions["engine"].connect() as conn:
            # 1) Pending inbound friend requests (with other user info)
            fr_stmt = (
                select(
                    FriendsTable.c.friendship_id,
                    FriendsTable.c.status,
                    FriendsTable.c.message,
                    FriendsTable.c.created_at_utc,
                    UsersTable.c.id.label("other_user_id"),
                    UsersTable.c.username.label("other_username"),
                    UsersTable.c.emoji.label("other_emoji"),
                    UsersTable.c.accent_color.label("other_color"),
                )
                .select_from(
                    FriendsTable.join(
                        UsersTable,
                        FriendsTable.c.friending_user_id == UsersTable.c.id,
                    )
                )
                .where(
                    and_(
                        FriendsTable.c.friended_user_id == user_id,
                        FriendsTable.c.status == "pending",
                    )
                )
                .order_by(FriendsTable.c.created_at_utc.desc())
            )
            fr_rows = conn.execute(fr_stmt).mappings().all()

            friend_requests = []
            for r in fr_rows:
                friend_requests.append(
                    {
                        "id": r["friendship_id"],
                        "status": r["status"],
                        "message": r["message"],
                        "created_at": r["created_at_utc"].isoformat() if r["created_at_utc"] else None,
                        "other_user": {
                            "id": r["other_user_id"],
                            "username": r["other_username"],
                            "emoji": r["other_emoji"],
                            "accent_color": r["other_color"],
                        },
                    }
                )

            # 2) Unseen reactions
            react_stmt = (
                select(
                    FeedReactionsTable.c.id,
                    FeedReactionsTable.c.reaction,
                    FeedReactionsTable.c.feed_kind,
                    FeedReactionsTable.c.feed_item_id,
                    FeedReactionsTable.c.created_at_utc,
                    UsersTable.c.id.label("actor_id"),
                    UsersTable.c.username.label("actor_username"),
                    UsersTable.c.emoji.label("actor_emoji"),
                    UsersTable.c.accent_color.label("actor_color"),
                )
                .select_from(
                    FeedReactionsTable.join(
                        UsersTable,
                        FeedReactionsTable.c.user_id == UsersTable.c.id,
                    )
                )
                .where(
                    and_(
                        FeedReactionsTable.c.recipient_id == user_id,
                        FeedReactionsTable.c.seen == False,
                    )
                )
                .order_by(FeedReactionsTable.c.created_at_utc.desc())
            )
            react_rows = conn.execute(react_stmt).mappings().all()

            reactions = []
            for r in react_rows:
                preview = build_feed_preview(conn, r["feed_kind"], r["feed_item_id"])
                reactions.append(
                    {
                        "id": r["id"],
                        "reaction": r["reaction"],
                        "created_at": r["created_at_utc"].isoformat() if r["created_at_utc"] else None,
                        "actor": {
                            "id": r["actor_id"],
                            "username": r["actor_username"],
                            "emoji": r["actor_emoji"],
                            "accent_color": r["actor_color"],
                        },
                        "feed": preview,
                    }
                )

            # 3) Unseen comments
            comment_stmt = (
                select(
                    FeedCommentsTable.c.id,
                    FeedCommentsTable.c.comment_text.label("comment"),
                    FeedCommentsTable.c.feed_kind,
                    FeedCommentsTable.c.feed_item_id,
                    FeedCommentsTable.c.created_at_utc,
                    UsersTable.c.id.label("actor_id"),
                    UsersTable.c.username.label("actor_username"),
                    UsersTable.c.emoji.label("actor_emoji"),
                    UsersTable.c.accent_color.label("actor_color"),
                )
                .select_from(
                    FeedCommentsTable.join(
                        UsersTable,
                        FeedCommentsTable.c.user_id == UsersTable.c.id,
                    )
                )
                .where(
                    and_(
                        FeedCommentsTable.c.recipient_id == user_id,
                        FeedCommentsTable.c.seen == False,
                    )
                )
                .order_by(FeedCommentsTable.c.created_at_utc.desc())
            )
            comment_rows = conn.execute(comment_stmt).mappings().all()

            comments = []
            for c in comment_rows:
                preview = build_feed_preview(conn, c["feed_kind"], c["feed_item_id"])
                comments.append(
                    {
                        "id": c["id"],
                        "comment": c["comment"],
                        "created_at": c["created_at_utc"].isoformat() if c["created_at_utc"] else None,
                        "actor": {
                            "id": c["actor_id"],
                            "username": c["actor_username"],
                            "emoji": c["actor_emoji"],
                            "accent_color": c["actor_color"],
                        },
                        "feed": preview,
                    }
                )

            # 4) Pending inbound actions (habits/rewards)
            pending = []
            ph_rows = conn.execute(
                _pending_select_with_category(PendingHabitsTable, include_category=True).where(
                    PendingHabitsTable.c.user_id == user_id
                )
            ).mappings().all()
            pending.extend(_pending_row_to_dict(r, "habit") for r in ph_rows)

            pr_rows = conn.execute(
                _pending_select_with_category(PendingRewardsTable, include_category=False).where(
                    PendingRewardsTable.c.user_id == user_id
                )
            ).mappings().all()
            pending.extend(_pending_row_to_dict(r, "reward") for r in pr_rows)

            pending.sort(key=lambda x: x.get("created_at_utc") or "", reverse=True)

        return jsonify(
            friend_requests=friend_requests,
            reactions=reactions,
            comments=comments,
            pending_actions=pending,
        )
    
    @api.post("/social/inbox/seen")
    @login_required
    def mark_inbox_seen():
        data = request.get_json(force=True) or {}
        user_id = g.user["id"]

        reaction_ids = data.get("reaction_ids") or []
        comment_ids  = data.get("comment_ids") or []

        with app.extensions["engine"].begin() as conn:
            if reaction_ids:
                conn.execute(
                    update(FeedReactionsTable)
                    .where(
                        and_(
                            FeedReactionsTable.c.id.in_(reaction_ids),
                            FeedReactionsTable.c.recipient_id == user_id,
                        )
                    )
                    .values(seen=True)
                )

            if comment_ids:
                conn.execute(
                    update(FeedCommentsTable)
                    .where(
                        and_(
                            FeedCommentsTable.c.id.in_(comment_ids),
                            FeedCommentsTable.c.recipient_id == user_id,
                        )
                    )
                    .values(seen=True)
                )

        return jsonify(ok=True)



    # ------------ END APP ------------ #
    app.register_blueprint(api)
    return app


app = create_app()



# 1. setup DB (mysql)
    # 1.1 start with USERS table
    # 1.2 then add GOALS and REWARDS and GOAL_LOG tables

# 2. create API endpoints (flask)
    # 1.1 START with a login / create user function 
    # 1.2 FIRST populate the day summarizer

# 3. Use gunicorn to stand it up
