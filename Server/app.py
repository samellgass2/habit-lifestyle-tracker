import os, secrets, hashlib
from datetime import datetime, timedelta, timezone, date
from calendar import monthrange
from flask import Flask, jsonify, request, g, make_response, Blueprint
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, select, delete, insert, func, update, and_, or_
from sqlalchemy.exc import SQLAlchemyError
from zoneinfo import ZoneInfo
from werkzeug.security import generate_password_hash, check_password_hash


from Server.models import UsersTable, SessionsTable, ReflectionsTable, AiProcessedReflectionsTable, create_all_tables, CategoriesTable, HabitsTable, CompletedHabitsTable, PointsSpendLedger

from Server.utils import compute_points, potential_points_for_habit

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

            # TODO: REMOVE THIS LATER: CREATES DEFAULT CATEGORY ON FIRST LOGIN. NEED 4 ME AND KASEY 4 TODAY
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

        with app.extensions["engine"].connect() as c:
            # common column set
            cols = [
                HabitsTable.c.id, HabitsTable.c.name, HabitsTable.c.type, HabitsTable.c.date_local,
                HabitsTable.c.base_value, HabitsTable.c.challenge, HabitsTable.c.importance,
                HabitsTable.c.time_minutes, HabitsTable.c.percent_target,
                CategoriesTable.c.emoji, CategoriesTable.c.color, CategoriesTable.c.points_mode,
            ]

            rec = c.execute(
                    select(*cols)
                    .join(CategoriesTable, HabitsTable.c.category_id == CategoriesTable.c.id)
                    .where(and_(HabitsTable.c.user_id == g.user["id"], HabitsTable.c.active == 1, HabitsTable.c.type == "recurring"))
                    .order_by(HabitsTable.c.created_at_utc.desc())
                ).mappings().all()

            one = c.execute(
                select(*cols)
                .join(CategoriesTable, HabitsTable.c.category_id == CategoriesTable.c.id)
                .where(and_(HabitsTable.c.user_id == g.user["id"], HabitsTable.c.active == 1,
                            HabitsTable.c.type == "one-off", HabitsTable.c.date_local == day_local))
                .order_by(HabitsTable.c.created_at_utc.desc())
            ).mappings().all()

            done_rows = c.execute(
                select(CompletedHabitsTable.c.habit_id)
                .where(and_(CompletedHabitsTable.c.user_id == g.user["id"], CompletedHabitsTable.c.day_local == day_local))
            ).all()
            done_today = {r[0] for r in done_rows if r[0] is not None}

        def shape(r):
            pm = r["points_mode"]
            pp = potential_points_for_habit(
                pm,
                r["base_value"], r["challenge"], r["importance"],
                time_target=r["time_minutes"], percent_target=r["percent_target"]
            )
            return {
                "id": r["id"],
                "name": r["name"],
                "type": r["type"],
                "date_local": r["date_local"].isoformat() if r["date_local"] else None,
                "category": {"emoji": r["emoji"], "color": r["color"]},
                "points_mode": pm,
                "potential_points": pp,            # <-- for UI label
                "completed_today": r["id"] in done_today,  # <-- disable button if true
            }

        habits = [*map(shape, one), *map(shape, rec)]
        return jsonify(habits=habits), 200
    
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

        with app.extensions["engine"].connect() as c:
            # 1) Earned today
            earned = c.execute(
                select(func.coalesce(func.sum(CompletedHabitsTable.c.points_awarded), 0))
                .where(and_(CompletedHabitsTable.c.user_id == g.user["id"],
                            CompletedHabitsTable.c.day_local == day_local))
            ).scalar() or 0.0

            # 2) Denominator: all relevant habits today
            rows = c.execute(
                select(
                    HabitsTable.c.id,
                    HabitsTable.c.base_value,
                    HabitsTable.c.challenge,
                    HabitsTable.c.importance,
                    HabitsTable.c.time_minutes,
                    HabitsTable.c.percent_target,
                    CategoriesTable.c.points_mode,
                    HabitsTable.c.type,
                    HabitsTable.c.date_local,
                    HabitsTable.c.active,
                )
                .join(CategoriesTable, HabitsTable.c.category_id == CategoriesTable.c.id)
                .where(and_(
                    HabitsTable.c.user_id == g.user["id"],
                    or_(
                        # include recurring only if still active
                        and_(HabitsTable.c.type == "recurring", HabitsTable.c.active == 1),
                        # include *all* one-offs for this local day, active or not (they may have just been auto-archived)
                        and_(HabitsTable.c.type == "one-off", HabitsTable.c.date_local == day_local),
                    )
                ))
            ).mappings().all()

        available = 0.0
        for r in rows:
            available += potential_points_for_habit(
                r["points_mode"],
                r["base_value"], r["challenge"], r["importance"],
                time_target=r["time_minutes"], percent_target=r["percent_target"]
            )

        progress = (float(earned) / available) if available > 0 else 0.0
        return jsonify(
            earned_today=float(round(earned, 2)),
            available_today=float(round(available, 2)),
            progress=max(0.0, min(1.0, progress)),
        ), 200

    @api.post("/habits/<int:hid>/complete")
    @login_required
    def complete_habit(hid):
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
                    CategoriesTable.c.id.label("cat_id"),
                    CategoriesTable.c.category_name.label("cat_name"),
                    CategoriesTable.c.points_mode.label("points_mode"),
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
            day_local = now_local.date()

            # Optional: prevent double-completion today
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
            if already:
                return jsonify(error="already completed today"), 409

            # Compute points
            pts = compute_points(
                pm,
                row["h_base"],
                row["h_chal"],
                row["h_imp"],
                time_minutes=time_minutes,
                percent_value=percent_value,
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
                active=1, created_at_utc=now, updated_at_utc=now
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