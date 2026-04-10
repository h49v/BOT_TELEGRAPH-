import aiosqlite
import os

DB_PATH = os.environ.get("DB_PATH", "cyberband.db")

# الوظائف القابلة للتفعيل/التعطيل
FEATURES = ["broadcast", "templates", "auto_reply", "groups_view", "stats_view"]

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                role TEXT DEFAULT 'sub',
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                group_id INTEGER PRIMARY KEY,
                title TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                content TEXT,
                media_path TEXT,
                media_type TEXT,
                buttons TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auto_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT UNIQUE,
                reply TEXT,
                buttons TEXT,
                active INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS broadcast_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_name TEXT,
                sent_count INTEGER,
                failed_count INTEGER,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                user_id INTEGER PRIMARY KEY,
                reason TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_name TEXT,
                schedule_time TEXT,
                repeat_interval INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                msg_count INTEGER DEFAULT 0,
                msg_delay INTEGER DEFAULT 30
            )
        """)
        try:
            await db.execute("ALTER TABLE scheduled_broadcasts ADD COLUMN msg_count INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE scheduled_broadcasts ADD COLUMN msg_delay INTEGER DEFAULT 30")
        except Exception:
            pass
        await db.execute("""
            CREATE TABLE IF NOT EXISTS userbot_sessions (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                session_string TEXT NOT NULL,
                saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # جدول الوظائف المفتوحة للعموم
        await db.execute("""
            CREATE TABLE IF NOT EXISTS feature_flags (
                feature TEXT PRIMARY KEY,
                enabled INTEGER DEFAULT 0
            )
        """)
        # إضافة الوظائف الافتراضية (كلها مغلقة بالبداية)
        for feature in FEATURES:
            await db.execute(
                "INSERT OR IGNORE INTO feature_flags (feature, enabled) VALUES (?, 0)",
                (feature,)
            )
        # Insert main admin from env
        main_admin = int(os.environ.get("MAIN_ADMIN_ID", 0))
        if main_admin:
            await db.execute(
                "INSERT OR IGNORE INTO admins (user_id, role) VALUES (?, 'main')",
                (main_admin,)
            )
        await db.commit()

# ─── Admin ────────────────────────────────────────────────
async def get_admin(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM admins WHERE user_id=?", (user_id,)) as cur:
            return await cur.fetchone()

async def get_all_admins():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, username, role FROM admins") as cur:
            return await cur.fetchall()

async def add_admin(user_id: int, username: str, role: str = "sub"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO admins (user_id, username, role) VALUES (?,?,?)",
            (user_id, username, role)
        )
        await db.commit()

async def remove_admin(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admins WHERE user_id=? AND role!='main'", (user_id,))
        await db.commit()

# ─── Groups ───────────────────────────────────────────────
async def get_all_groups():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT group_id, title, active FROM groups") as cur:
            return await cur.fetchall()

async def get_active_groups():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT group_id, title FROM groups WHERE active=1") as cur:
            return await cur.fetchall()

async def add_group(group_id: int, title: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO groups (group_id, title) VALUES (?,?)",
            (group_id, title)
        )
        await db.commit()

async def remove_group(group_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM groups WHERE group_id=?", (group_id,))
        await db.commit()

async def toggle_group(group_id: int, active: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE groups SET active=? WHERE group_id=?", (active, group_id))
        await db.commit()

# ─── Templates ────────────────────────────────────────────
async def get_all_templates():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, name, content, media_type, buttons FROM templates") as cur:
            return await cur.fetchall()

async def get_template(name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, name, content, media_path, media_type, buttons FROM templates WHERE name=?", (name,)
        ) as cur:
            return await cur.fetchone()

async def add_template(name: str, content: str, media_path: str = None, media_type: str = None, buttons: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO templates (name, content, media_path, media_type, buttons) VALUES (?,?,?,?,?)",
            (name, content, media_path, media_type, buttons)
        )
        await db.commit()

async def delete_template(name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM templates WHERE name=?", (name,))
        await db.commit()

# ─── Auto Replies ─────────────────────────────────────────
async def get_all_replies():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, keyword, reply, buttons, active FROM auto_replies") as cur:
            return await cur.fetchall()

async def get_reply_by_keyword(keyword: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM auto_replies WHERE keyword=? AND active=1", (keyword.lower(),)
        ) as cur:
            return await cur.fetchone()

async def add_reply(keyword: str, reply: str, buttons: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO auto_replies (keyword, reply, buttons) VALUES (?,?,?)",
            (keyword.lower(), reply, buttons)
        )
        await db.commit()

async def delete_reply(keyword: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM auto_replies WHERE keyword=?", (keyword.lower(),))
        await db.commit()

async def toggle_reply(reply_id: int, active: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE auto_replies SET active=? WHERE id=?", (active, reply_id))
        await db.commit()

# ─── Blacklist ────────────────────────────────────────────
async def is_blacklisted(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM blacklist WHERE user_id=?", (user_id,)) as cur:
            return await cur.fetchone() is not None

async def add_blacklist(user_id: int, reason: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO blacklist (user_id, reason) VALUES (?,?)",
            (user_id, reason)
        )
        await db.commit()

async def remove_blacklist(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM blacklist WHERE user_id=?", (user_id,))
        await db.commit()

async def get_blacklist():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, reason, added_at FROM blacklist") as cur:
            return await cur.fetchall()

# ─── Broadcast Log ────────────────────────────────────────
async def log_broadcast(template_name: str, sent: int, failed: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO broadcast_log (template_name, sent_count, failed_count) VALUES (?,?,?)",
            (template_name, sent, failed)
        )
        await db.commit()

async def get_broadcast_logs(limit: int = 20):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT template_name, sent_count, failed_count, sent_at FROM broadcast_log ORDER BY sent_at DESC LIMIT ?",
            (limit,)
        ) as cur:
            return await cur.fetchall()

# ─── Stats ────────────────────────────────────────────────
async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        stats = {}
        async with db.execute("SELECT COUNT(*) FROM groups WHERE active=1") as cur:
            stats["active_groups"] = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM groups") as cur:
            stats["total_groups"] = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM templates") as cur:
            stats["templates"] = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM auto_replies WHERE active=1") as cur:
            stats["auto_replies"] = (await cur.fetchone())[0]
        async with db.execute("SELECT SUM(sent_count), COUNT(*) FROM broadcast_log") as cur:
            row = await cur.fetchone()
            stats["total_sent"] = row[0] or 0
            stats["total_broadcasts"] = row[1] or 0
        async with db.execute("SELECT COUNT(*) FROM blacklist") as cur:
            stats["blacklisted"] = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM admins") as cur:
            stats["admins"] = (await cur.fetchone())[0]
        return stats

# ─── Scheduled ────────────────────────────────────────────
async def get_scheduled():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM scheduled_broadcasts WHERE active=1") as cur:
            return await cur.fetchall()

async def add_scheduled(template_name: str, schedule_time: str, repeat_interval: int = 0, msg_count: int = 0, msg_delay: int = 30):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO scheduled_broadcasts (template_name, schedule_time, repeat_interval, msg_count, msg_delay) VALUES (?,?,?,?,?)",
            (template_name, schedule_time, repeat_interval, msg_count, msg_delay)
        )
        await db.commit()

async def remove_scheduled(schedule_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM scheduled_broadcasts WHERE id=?", (schedule_id,))
        await db.commit()

# ─── Userbot Sessions ─────────────────────────────────────
async def save_session(session_string: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO userbot_sessions (id, session_string) VALUES (1, ?)",
            (session_string,)
        )
        await db.commit()

async def get_session():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT session_string FROM userbot_sessions WHERE id=1") as cur:
            return await cur.fetchone()

async def delete_session():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM userbot_sessions WHERE id=1")
        await db.commit()

# ─── Feature Flags ────────────────────────────────────────
async def is_feature_enabled(feature: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT enabled FROM feature_flags WHERE feature=?", (feature,)
        ) as cur:
            row = await cur.fetchone()
            return bool(row and row[0])

async def set_feature(feature: str, enabled: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO feature_flags (feature, enabled) VALUES (?, ?)",
            (feature, int(enabled))
        )
        await db.commit()

async def get_all_features() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT feature, enabled FROM feature_flags") as cur:
            rows = await cur.fetchall()
            return {r[0]: bool(r[1]) for r in rows}
