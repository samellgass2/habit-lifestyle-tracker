import os, secrets, hashlib
from datetime import datetime, timedelta, timezone, date
from calendar import monthrange
from flask import Flask, jsonify, request, g, make_response, Blueprint
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, select, delete, insert, func, update, and_
from sqlalchemy.exc import SQLAlchemyError
from zoneinfo import ZoneInfo
from werkzeug.security import generate_password_hash, check_password_hash


from Server.models import UsersTable, SessionsTable, ReflectionsTable, AiProcessedReflectionsTable, create_all_tables

# ----------- CONTROL FLAGS / DEFAULTS --------- #
LAZY_SESSION_CLEANUP = True # If there is no cron or watcher process to remove stale sessions, do it on each successful login
api = Blueprint('api', __name__, url_prefix='/api')



# ----------- 🍪🍪🍪 COOKIE CONFIG 🍪🍪🍪 ----------- #
SESSION_COOKIE_NAME = "hab_life_sesh"
SESSION_LIFETIME = timedelta(hours=2)
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
    CORS(app, resources={r"/*": {"origins": origins or ["https://app-dev.samellgass.com"]}}, methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     supports_credentials=True)

    # --- DB engine ---
    engine = _make_engine()
    app.extensions = getattr(app, "extensions", {})
    app.extensions["engine"] = engine

    def _clear_expired_sessions():
        with engine.begin() as conn:
            res = conn.execute(delete(SessionsTable).where(SessionsTable.c.expires_at < _now_utc()))
            print("Cleared expired session tokens. {} rows were removed.".format(res.rowcount))

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

        max_age = int(SESSION_LIFETIME.total_seconds())
        resp = jsonify(ok=True, userId=row["id"])
        resp.set_cookie(
            SESSION_COOKIE_NAME, raw_token,
            max_age=max_age, httponly=COOKIE_HTTPONLY, secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE, path="/"
        )

        if LAZY_SESSION_CLEANUP:
            _clear_expired_sessions()
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
        print("SANITY: we got payload", data)

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
        Returns an object with: {scope, label, available, summary?, message?, today_has_reflection?}
        """
        scope = (request.args.get("scope") or "day").lower()
        if scope not in ("day", "week", "month"):
            return jsonify(error="invalid scope"), 400

        tz = g.user.get("timezone") or "UTC"
        today_local = today_local_date(tz)

        # Figure out target window + label
        if scope == "day":
            target_day = today_local - timedelta(days=1)  # Yesterday, local
            label = "Yesterday"
            # Try AI first
            with app.extensions["engine"].connect() as c:
                ai = c.execute(
                    select(AiProcessedReflectionsTable.c.summary)
                    .where(and_(
                        AiProcessedReflectionsTable.c.user_id == g.user["id"],
                        AiProcessedReflectionsTable.c.scope == "day",
                        AiProcessedReflectionsTable.c.kind == "summary",
                        AiProcessedReflectionsTable.c.target_date == target_day
                    ))
                ).scalar()
                if ai:
                    return jsonify(scope="day", label=label, available=True, summary=ai), 200

                # No AI yet: check “today” raw reflection (so we can show a friendly prompt)
                today_row = c.execute(
                    select(ReflectionsTable.c.id)
                    .where(and_(ReflectionsTable.c.user_id == g.user["id"],
                                ReflectionsTable.c.day_local == today_local))
                ).scalar()
            # Craft message
            if today_row:
                msg = "You didn't enter a reflection yesterday. But you did today, so check back tomorrow!"
                return jsonify(scope="day", label=label, available=False, message=msg, today_has_reflection=True), 200
            else:
                msg = "You didn't enter a reflection yesterday. If you want to see a summary for tomorrow, enter one today!"
                return jsonify(scope="day", label=label, available=False, message=msg, today_has_reflection=False), 200

        # WEEK / MONTH
        if scope == "week":
            start, end = _week_start_end(today_local)
            label = "This Week"
        else:
            start, end = _month_start_end(today_local)
            label = "This Month"

        with app.extensions["engine"].connect() as c:
            ai = c.execute(
                select(AiProcessedReflectionsTable.c.summary)
                .where(and_(
                    AiProcessedReflectionsTable.c.user_id == g.user["id"],
                    AiProcessedReflectionsTable.c.scope == scope,
                    AiProcessedReflectionsTable.c.kind == "summary",
                    AiProcessedReflectionsTable.c.period_start == start,
                    AiProcessedReflectionsTable.c.period_end == end,
                ))
            ).scalar()

        if ai:
            return jsonify(scope=scope, label=label, available=True, summary=ai), 200
        else:
            return jsonify(scope=scope, label=label, available=False,
                        message=f"No {scope} summary yet. It will appear once the period completes."), 200

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