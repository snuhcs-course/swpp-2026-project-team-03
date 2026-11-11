"""Members, bands and shared scores in one SQLite file (ROCKY_HOME/rocky.db).

The app used to keep these on each phone, so two phones could not be in the same band.
The tables match the app's old local ones (UserDatabase, BandDatabase); band members and
shared scores read nicknames from `users`, so a nickname change shows everywhere at once.

Passwords are hashed with PBKDF2-HMAC-SHA256 in the app's format
("pbkdf2-sha256$<iterations>$<salt b64>$<hash b64>"). A login gets a random token; only its
SHA-256 is stored.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

INSTRUMENTS = ("piano", "drums", "bass", "guitar", "vocal")  # app order
BAND_PARTS = ("piano", "drums", "bass", "guitar", "guitar2", "vocal")
CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L
CODE_LENGTH = 6
NAME_MAX = 20
OLD_DEMO_CODE = "BAND33"  # the removed demo band; see Accounts._remove_old_demo
ITERATIONS = 120_000

# Same rules as the app's SignUpValidator.
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
NICK_RE = re.compile(r"^[가-힣A-Za-z0-9_]{2,12}$")


class AccountError(Exception):
    """A request the rules do not allow. `status` is the HTTP code, `field` the form field."""

    def __init__(self, status: int, message: str, field: str | None = None):
        super().__init__(message)
        self.status, self.message, self.field = status, message, field


@dataclass
class User:
    id: int
    email: str
    nickname: str
    instruments: list[str]
    provider: str
    created_at: int

    def json(self) -> dict:
        return {"id": self.id, "email": self.email, "nickname": self.nickname,
                "instruments": self.instruments, "provider": self.provider, "created_at": self.created_at}


def now_ms() -> int:
    return int(time.time() * 1000)


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations, 32)
    b64 = base64.b64encode
    return f"pbkdf2-sha256${iterations}${b64(salt).decode()}${b64(key).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    parts = (stored or "").split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2-sha256" or not parts[1].isdigit():
        return False
    try:
        salt, expected = base64.b64decode(parts[2]), base64.b64decode(parts[3])
    except ValueError:
        return False
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(parts[1]), len(expected))
    return hmac.compare_digest(key, expected)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_code(code: str) -> str:
    return "".join(c for c in code if not c.isspace() and c != "-").upper()


def clean_instruments(items) -> list[str]:
    wanted = {str(i) for i in items or []}
    return [i for i in INSTRUMENTS if i in wanted]


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT,
    nickname      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    instruments   TEXT    NOT NULL DEFAULT '',
    auth_provider TEXT    NOT NULL DEFAULT 'EMAIL',
    terms_agreed_at INTEGER NOT NULL,
    created_at    INTEGER NOT NULL,
    last_login_at INTEGER
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT    PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bands (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    invite_code TEXT    NOT NULL UNIQUE,
    owner_id    INTEGER NOT NULL REFERENCES users(id),
    created_at  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS band_members (
    band_id    INTEGER NOT NULL REFERENCES bands(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    instrument TEXT    NOT NULL,
    joined_at  INTEGER NOT NULL,
    PRIMARY KEY (band_id, user_id)
);
CREATE TABLE IF NOT EXISTS shared_scores (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    band_id     INTEGER NOT NULL REFERENCES bands(id) ON DELETE CASCADE,
    work_id     INTEGER NOT NULL,
    job_id      TEXT,
    title       TEXT    NOT NULL,
    instruments TEXT    NOT NULL,
    work_date   TEXT    NOT NULL,
    original    TEXT    NOT NULL DEFAULT '',
    shared_by   INTEGER NOT NULL REFERENCES users(id),
    shared_at   INTEGER NOT NULL,
    UNIQUE (band_id, work_id)
);
CREATE INDEX IF NOT EXISTS idx_members_user ON band_members(user_id);
CREATE INDEX IF NOT EXISTS idx_scores_job ON shared_scores(job_id);
-- Star ratings (1-5) the app collects under each score, to see which results need work.
-- One row per score and rater; rater 0 is someone who was not logged in. Kept after the job is deleted.
CREATE TABLE IF NOT EXISTS ratings (
    job_id      TEXT    NOT NULL,
    rater       INTEGER NOT NULL DEFAULT 0,
    stars       INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 5),
    title       TEXT    NOT NULL DEFAULT '',
    instruments TEXT    NOT NULL DEFAULT '',
    rated_at    INTEGER NOT NULL,
    PRIMARY KEY (job_id, rater)
);
"""


class Accounts:
    """All member and band rules. One connection behind a lock: the API runs in one Pod."""

    def __init__(self, path: Path | str, clock=now_ms):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self.lock = threading.RLock()
        self.clock = clock
        with self.lock:
            self.db.executescript(SCHEMA)
            self._remove_old_demo()

    # ---------- helpers ----------

    def _tx(self):
        return _Tx(self)

    def _one(self, sql: str, *args):
        return self.db.execute(sql, args).fetchone()

    def _user(self, row) -> User:
        return User(row["id"], row["email"], row["nickname"],
                    [i for i in row["instruments"].split(",") if i], row["auth_provider"], row["created_at"])

    def user(self, user_id: int) -> User | None:
        row = self._one("SELECT * FROM users WHERE id = ?", user_id)
        return self._user(row) if row else None

    def _new_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        now = self.clock()
        self.db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (_token_hash(token), user_id, now))
        self.db.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, user_id))
        return token

    # ---------- members ----------

    def email_taken(self, email: str) -> bool:
        return self._one("SELECT 1 FROM users WHERE email = ?", normalize_email(email)) is not None

    def nickname_taken(self, nickname: str, except_user: int | None = None) -> bool:
        return self._one("SELECT 1 FROM users WHERE nickname = ? COLLATE NOCASE AND id != ?",
                         nickname.strip(), except_user or 0) is not None

    def sign_up(self, email: str, password: str, nickname: str, instruments) -> tuple[User, str]:
        email, nickname = normalize_email(email), nickname.strip()
        if len(email) > 254 or not EMAIL_RE.match(email):
            raise AccountError(422, "이메일 형식이 올바르지 않아요", "email")
        if (not 8 <= len(password) <= 64 or any(c.isspace() for c in password)
                or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password)):
            raise AccountError(422, "비밀번호는 영문과 숫자를 섞어 8~64자로 정해 주세요", "password")
        if not NICK_RE.match(nickname):
            raise AccountError(422, "닉네임은 한글, 영문, 숫자, _로 2~12자예요", "nickname")
        hashed = hash_password(password)  # slow; outside the lock
        with self.lock, self._tx():
            if self.email_taken(email):
                raise AccountError(409, "이미 가입된 이메일이에요", "email")
            if self.nickname_taken(nickname):
                raise AccountError(409, "이미 사용 중인 닉네임이에요", "nickname")
            now = self.clock()
            cur = self.db.execute(
                "INSERT INTO users (email, password_hash, nickname, instruments, terms_agreed_at, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (email, hashed, nickname, ",".join(clean_instruments(instruments)), now, now))
            token = self._new_session(cur.lastrowid)
            return self.user(cur.lastrowid), token

    def login(self, email: str, password: str) -> tuple[User, str] | None:
        row = self._one("SELECT * FROM users WHERE email = ?", normalize_email(email))
        if row is None or not verify_password(password, row["password_hash"]):
            return None
        with self.lock:
            return self._user(row), self._new_session(row["id"])

    def user_for_token(self, token: str) -> User | None:
        row = self._one("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
                        _token_hash(token))
        return self._user(row) if row else None

    def logout(self, token: str) -> None:
        with self.lock:
            self.db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))

    def update_profile(self, user: User, nickname: str, instruments) -> User:
        nickname = nickname.strip()
        if not NICK_RE.match(nickname):
            raise AccountError(422, "닉네임은 한글, 영문, 숫자, _로 2~12자예요", "nickname")
        with self.lock, self._tx():
            if self.nickname_taken(nickname, user.id):
                raise AccountError(409, "이미 사용 중인 닉네임이에요", "nickname")
            self.db.execute("UPDATE users SET nickname = ?, instruments = ? WHERE id = ?",
                            (nickname, ",".join(clean_instruments(instruments)), user.id))
            return self.user(user.id)

    # ---------- bands ----------

    def _band(self, band_id: int):
        row = self._one("SELECT * FROM bands WHERE id = ?", band_id)
        if row is None:
            raise AccountError(404, "밴드를 찾을 수 없어요")
        return row

    def _member_band(self, user: User, band_id: int):
        band = self._band(band_id)
        if self._one("SELECT 1 FROM band_members WHERE band_id = ? AND user_id = ?", band_id, user.id) is None:
            raise AccountError(403, "이 밴드의 멤버가 아니에요")
        return band

    @staticmethod
    def _band_json(row) -> dict:
        return {"id": row["id"], "name": row["name"], "invite_code": row["invite_code"],
                "owner_id": row["owner_id"], "created_at": row["created_at"]}

    @staticmethod
    def _check_name(name: str) -> str:
        name = name.strip()
        if not name:
            raise AccountError(422, "밴드 이름을 입력해 주세요", "name")
        if len(name) > NAME_MAX:
            raise AccountError(422, f"밴드 이름은 {NAME_MAX}자까지 쓸 수 있어요", "name")
        return name

    @staticmethod
    def _check_part(instrument: str) -> str:
        if instrument not in BAND_PARTS:
            raise AccountError(422, "맡을 악기를 골라 주세요", "instrument")
        return instrument

    def bands_of(self, user: User) -> list[dict]:
        rows = self.db.execute(
            """SELECT b.*, m.instrument AS my_instrument,
                      (SELECT COUNT(*) FROM band_members x WHERE x.band_id = b.id) AS member_count,
                      (SELECT COUNT(*) FROM shared_scores s WHERE s.band_id = b.id) AS score_count
               FROM bands b JOIN band_members m ON m.band_id = b.id
               WHERE m.user_id = ? ORDER BY m.joined_at DESC, b.id DESC""", (user.id,)).fetchall()
        return [{"band": self._band_json(r), "member_count": r["member_count"], "score_count": r["score_count"],
                 "my_instrument": r["my_instrument"]} for r in rows]

    def detail(self, user: User, band_id: int) -> dict:
        band = self._member_band(user, band_id)
        members = self.db.execute(
            """SELECT m.user_id, u.nickname, m.instrument FROM band_members m JOIN users u ON u.id = m.user_id
               WHERE m.band_id = ? ORDER BY m.joined_at, m.user_id""", (band_id,)).fetchall()
        scores = self.db.execute(
            """SELECT s.*, u.nickname AS shared_by_name FROM shared_scores s JOIN users u ON u.id = s.shared_by
               WHERE s.band_id = ? ORDER BY s.shared_at DESC, s.id DESC""", (band_id,)).fetchall()
        return {
            "band": self._band_json(band),
            "members": [{"user_id": m["user_id"], "nickname": m["nickname"], "instrument": m["instrument"],
                         "is_owner": m["user_id"] == band["owner_id"]} for m in members],
            "scores": [{"id": s["id"], "work_id": s["work_id"], "job_id": s["job_id"], "title": s["title"],
                        "instruments": [i for i in s["instruments"].split(",") if i], "date": s["work_date"],
                        "original": [i for i in s["original"].split(",") if i], "shared_by": s["shared_by"],
                        "shared_by_name": s["shared_by_name"], "shared_at": s["shared_at"]} for s in scores],
        }

    def create_band(self, user: User, name: str, instrument: str) -> dict:
        name, instrument = self._check_name(name), self._check_part(instrument)
        with self.lock, self._tx():
            for _ in range(20):
                code = "".join(secrets.choice(CODE_CHARS) for _ in range(CODE_LENGTH))
                if self._one("SELECT 1 FROM bands WHERE invite_code = ?", code) is None:
                    break
            else:
                raise AccountError(503, "초대 코드를 만들지 못했어요. 다시 시도해 주세요")
            now = self.clock()
            cur = self.db.execute("INSERT INTO bands (name, invite_code, owner_id, created_at) VALUES (?, ?, ?, ?)",
                                  (name, code, user.id, now))
            self.db.execute("INSERT INTO band_members VALUES (?, ?, ?, ?)", (cur.lastrowid, user.id, instrument, now))
            return self._band_json(self._band(cur.lastrowid))

    def join(self, user: User, code: str, instrument: str) -> dict:
        code, instrument = normalize_code(code), self._check_part(instrument)
        if len(code) != CODE_LENGTH or any(c not in CODE_CHARS for c in code):
            raise AccountError(422, f"초대 코드는 영문·숫자 {CODE_LENGTH}자리예요", "code")
        with self.lock, self._tx():
            band = self._one("SELECT * FROM bands WHERE invite_code = ?", code)
            if band is None:
                raise AccountError(404, "이 초대 코드로 된 밴드가 없어요", "code")
            if self._one("SELECT 1 FROM band_members WHERE band_id = ? AND user_id = ?", band["id"], user.id):
                raise AccountError(409, "이미 참여 중인 밴드예요", "code")
            self.db.execute("INSERT INTO band_members VALUES (?, ?, ?, ?)",
                            (band["id"], user.id, instrument, self.clock()))
            return self._band_json(band)

    def leave(self, user: User, band_id: int) -> None:
        with self.lock, self._tx():
            band = self._member_band(user, band_id)
            self.db.execute("DELETE FROM band_members WHERE band_id = ? AND user_id = ?", (band_id, user.id))
            first = self._one("SELECT user_id FROM band_members WHERE band_id = ? ORDER BY joined_at, user_id",
                              band_id)
            if first is None:  # the last member left: the band goes too
                self.db.execute("DELETE FROM bands WHERE id = ?", (band_id,))
            elif band["owner_id"] == user.id:  # the earliest member becomes the owner
                self.db.execute("UPDATE bands SET owner_id = ? WHERE id = ?", (first["user_id"], band_id))

    def rename_band(self, user: User, band_id: int, name: str) -> dict:
        name = self._check_name(name)
        with self.lock, self._tx():
            band = self._member_band(user, band_id)
            if band["owner_id"] != user.id:
                raise AccountError(403, "방장만 밴드 이름을 바꿀 수 있어요")
            self.db.execute("UPDATE bands SET name = ? WHERE id = ?", (name, band_id))
            return self._band_json(self._band(band_id))

    # ---------- shared scores ----------

    def share(self, user: User, band_id: int, work: dict) -> bool:
        """True if newly shared, False if this band already has the score."""
        with self.lock, self._tx():
            self._member_band(user, band_id)
            job_id = work.get("job_id") or None
            if job_id is not None and not re.fullmatch(r"[0-9a-f]{12}", str(job_id)):
                raise AccountError(422, "작업 번호가 올바르지 않아요", "job_id")
            title = str(work.get("title", "")).strip()[:120]
            if not title:
                raise AccountError(422, "악보 제목이 없어요", "title")
            cur = self.db.execute(
                """INSERT OR IGNORE INTO shared_scores
                   (band_id, work_id, job_id, title, instruments, work_date, original, shared_by, shared_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (band_id, int(work["work_id"]), job_id, title,
                 ",".join(str(i) for i in work.get("instruments", [])), str(work.get("date", "")),
                 ",".join(str(i) for i in work.get("original", [])), user.id, self.clock()))
            return cur.rowcount == 1

    def rename_score(self, user: User, band_id: int, score_id: int, title: str) -> None:
        title = title.strip()[:120]
        if not title:
            raise AccountError(422, "악보 이름을 입력해 주세요", "title")
        with self.lock, self._tx():
            band = self._member_band(user, band_id)
            row = self._one("SELECT shared_by FROM shared_scores WHERE id = ? AND band_id = ?", score_id, band_id)
            if row is None:
                raise AccountError(404, "공유된 악보를 찾을 수 없어요")
            if row["shared_by"] != user.id and band["owner_id"] != user.id:
                raise AccountError(403, "공유한 사람이나 방장만 이름을 바꿀 수 있어요")
            self.db.execute("UPDATE shared_scores SET title = ? WHERE id = ?", (title, score_id))

    def rename_my_work(self, user: User, work_id: int, title: str) -> None:
        title = title.strip()[:120]
        if title:
            with self.lock:
                self.db.execute("UPDATE shared_scores SET title = ? WHERE shared_by = ? AND work_id = ?",
                                (title, user.id, work_id))

    def work_shared(self, user: User, work_id: int) -> bool:
        return self._one("SELECT 1 FROM shared_scores WHERE shared_by = ? AND work_id = ?", user.id, work_id) is not None

    def job_shared(self, job_id: str) -> bool:
        """Band members open a shared score from the server, so its job must not be deleted."""
        return self._one("SELECT 1 FROM shared_scores WHERE job_id = ?", job_id) is not None

    # ---------- ratings ----------

    def rate(self, job_id: str, stars, rater: User | None, title: str = "", instruments=()) -> dict:
        """Save (or change) one rater's stars for a score."""
        if isinstance(stars, bool) or not isinstance(stars, int) or not 1 <= stars <= 5:
            raise AccountError(422, "별점은 1에서 5 사이예요", "stars")
        parts = [i for i in instruments if i in BAND_PARTS] if isinstance(instruments, list) else []
        with self._tx():
            self.db.execute(
                """INSERT INTO ratings (job_id, rater, stars, title, instruments, rated_at) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (job_id, rater) DO UPDATE SET stars = excluded.stars, title = excluded.title,
                   instruments = excluded.instruments, rated_at = excluded.rated_at""",
                (job_id, rater.id if rater else 0, stars, str(title)[:200], ",".join(parts), self.clock()))
        return {"job_id": job_id, "stars": stars}

    def ratings(self) -> dict:
        """Every rating, newest first, with the count and average (for the team)."""
        rows = self.db.execute("SELECT * FROM ratings ORDER BY rated_at DESC").fetchall()
        items = [{"job_id": r["job_id"], "stars": r["stars"], "title": r["title"],
                  "instruments": [i for i in r["instruments"].split(",") if i], "rated_at": r["rated_at"],
                  "logged_in": r["rater"] != 0} for r in rows]
        average = round(sum(i["stars"] for i in items) / len(items), 2) if items else None
        histogram = {str(n): sum(1 for i in items if i["stars"] == n) for n in range(1, 6)}
        return {"count": len(items), "average": average, "histogram": histogram, "ratings": items}

    # ---------- old demo data ----------

    def _remove_old_demo(self) -> None:
        """Earlier versions seeded a demo band (invite code BAND33) with three members who could not
        log in and a demo song that only existed inside the app. The demo was removed on 2026-11-11, so
        delete that band and those placeholder members if an older database still has them."""
        with self._tx():
            self.db.execute("DELETE FROM shared_scores WHERE shared_by IN"
                            " (SELECT id FROM users WHERE email LIKE 'demo_@rocky.invalid' AND password_hash IS NULL)")
            self.db.execute("DELETE FROM bands WHERE invite_code = ? AND owner_id IN"
                            " (SELECT id FROM users WHERE email LIKE 'demo_@rocky.invalid' AND password_hash IS NULL)",
                            (OLD_DEMO_CODE,))
            self.db.execute("DELETE FROM users WHERE email LIKE 'demo_@rocky.invalid' AND password_hash IS NULL")


class _Tx:
    """BEGIN … COMMIT, or ROLLBACK on an error. Nested use joins the outer transaction."""

    def __init__(self, acc: Accounts):
        self.acc, self.outer = acc, False

    def __enter__(self):
        self.outer = not self.acc.db.in_transaction
        if self.outer:
            self.acc.db.execute("BEGIN IMMEDIATE")

    def __exit__(self, exc_type, *_):
        if self.outer:
            self.acc.db.execute("ROLLBACK" if exc_type else "COMMIT")
        return False
