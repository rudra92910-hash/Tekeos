import asyncio
import aiohttp
import sqlite3
import json
import os
import re
import string
import random
import html
from datetime import datetime, timedelta
from typing import Optional
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ChatJoinRequest,
)
from telegram.error import BadRequest
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

# BOT (primary) — @UKRAINEBSTBOT
# Keep secrets out of source code. Set BOT_TOKEN in Railway Variables.
BOT_TOKEN = os.getenv("BOT_TOKEN", "8974312835:AAF3UVR98ZHQEvFkI8IGtSRxO9Pwek1kQ68").strip()

NEW_BOT_USERNAME = "UKRAINEBSTBOT"
NEW_BOT_START_LINK = "https://t.me/UKRAINEBSTBOT?start=ref_7EPRSGYI"

# Updated invite links + fixed numeric chat IDs for membership checks
MAIN_CHANNEL_INVITE = "https://t.me/THEBOTBST"
BACKUP_CHANNEL_INVITE = "https://t.me/UKRAINEDEVBOTS"
THIRD_CHANNEL_INVITE = "https://t.me/+QtvG4PVdADE0MjFl"
THIRD_CHANNEL_ID = "-1004429791979"
FOURTH_CHANNEL_INVITE = "https://t.me/+QM-ka73xm_ZiMDQ1"
FOURTH_CHANNEL_ID = "-1003591557802"
GROUP_INVITE = "https://t.me/+xTs7ATuY6pBlODQ1"
# User MUST join Main Channel + Backup Channel + Group before Verify works.
CHANNEL_USERNAME = "@THEBOTBST"          # Main channel public username
CHANNEL_USERNAME2 = "@UKRAINEDEVBOTS"    # Backup channel public username
GROUP_USERNAME = "+xTs7ATuY6pBlODQ1"      # Invite-only group
# Hardcoded chat IDs (also forced into bot_settings on every start)
MAIN_CHANNEL_ID = "-1003872884843"
BACKUP_CHANNEL_ID = "-1004495453622"
GROUP_CHAT_ID = "-1003961551741"
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "bot.db")).strip()

# Only these 3 owners — full access + only they can broadcast
OWNER_IDS = [8416912035, 7746126705, 899]
# Static admin IDs (fallback); dynamic admins are stored in DB
ADMIN_IDS = [893099]

# Credit limits
MAX_USER_CREDITS = 500000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000  # maximum balance; new users start with 5 credits
START_USER_CREDITS = 3000
REFERRAL_CREDITS = 25
OWNER_CREDITS = 9223372036500000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000854775807
ADMIN_CREDITS = 9223372036855000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000004775807
MAX_FILTER_KEYS = 1000
SUBSCRIBE_WAIT_SECONDS = 5
OVER_LIMIT_REFILL_CREDITS = 2000
OVER_LIMIT_WAIT_SECONDS = 3600  # 1 hour

WAITING_REDEEM_CODE = 1
WAITING_BROADCAST_MSG = 2
WAITING_API_VALUE = 3
WAITING_BROADCAST_BTN_CHOICE = 4
WAITING_BROADCAST_BTN_URL = 5
WAITING_BROADCAST_BTN_TEXT = 6
WAITING_BROADCAST_BTN_EMOJI = 7
WAITING_BROADCAST_COMMENT = 8
WAITING_ADD_LINK = 9

# Active broadcast tasks keyed by broadcaster user id (for stop support)
ACTIVE_BROADCAST_TASKS: dict = {}


# ═══════════════════════════════════════════════════
#             DYNAMIC ADMIN FUNCTIONS
# ═══════════════════════════════════════════════════

def get_dynamic_admins() -> list:
    """Return list of dynamically added admin IDs from DB."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT telegram_id FROM bot_admins")
        rows = c.fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def add_dynamic_admin(tid: int) -> bool:
    """Add a dynamic admin to DB. Returns False if already admin/owner."""
    if tid in OWNER_IDS or tid in ADMIN_IDS:
        return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO bot_admins (telegram_id) VALUES (?)", (tid,))
    added = c.rowcount > 0
    conn.commit()
    conn.close()
    return added


def remove_dynamic_admin(tid: int) -> bool:
    """Remove a dynamic admin from DB."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM bot_admins WHERE telegram_id = ?", (tid,))
    removed = c.rowcount > 0
    conn.commit()
    conn.close()
    return removed


def is_owner(uid: int) -> bool:
    """Owner has unrestricted access to every feature."""
    return uid in OWNER_IDS


def is_admin(uid: int) -> bool:
    """Admin has the restricted permission set. Checks static + dynamic admins."""
    return uid in ADMIN_IDS or uid in get_dynamic_admins()


def is_staff(uid: int) -> bool:
    """Owner or Admin — i.e. any privileged user."""
    return is_owner(uid) or is_admin(uid)


def get_all_staff_ids() -> list:
    """Return unique list of all owner + static admin + dynamic admin IDs."""
    ids = list(OWNER_IDS) + list(ADMIN_IDS) + get_dynamic_admins()
    seen = set()
    out = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


# ═══════════════════════════════════════════════════
#                 PREMIUM EMOJI
# ═══════════════════════════════════════════════════

def E(emoji_id: str, fallback: str) -> str:
    """Premium custom emoji HTML tag (Bot API). Fallback is shown only if client cannot render it."""
    eid = str(emoji_id).strip()
    fb = str(fallback) if fallback else "•"
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'


_EMOJI = [
    # Old emojis (keeping as is)
    ("5039775669496579510", "⭐"),   # 0 - Star
    ("5041994565565809886", "🔥"),   # 1 - Fire
    ("5042302287087666158", "💎"),   # 2 - Diamond
    ("5039623284056917259", "⚡"),   # 3 - Lightning
    ("5042050649248760772", "🌟"),   # 4 - Glowing Star
    ("5039560388555834382", "✨"),   # 5 - Sparkles
    ("5042101437237036298", "🎯"),   # 6 - Target
    ("5039544445637231745", "🚀"),   # 7 - Rocket
    ("5039539210072097557", "💫"),   # 8 - Dizzy
    ("5040018571372004272", "🏆"),   # 9 - Trophy
    ("5042274086332400375", "👑"),   # 10 - Crown
    ("5206607081334906820", "💥"),   # 11 - Collision
    ("5409048419211682843", "🎪"),   # 12 - Circus Tent
    ("5397782960512444700", "🎭"),   # 13 - Performing Arts
    ("5269531045165816230", "🎨"),   # 14 - Artist Palette
    ("5424818078833715060", "🎬"),   # 15 - Movie Camera
    ("5341498088408234504", "🌈"),   # 16 - Rainbow
    ("5258513401784573443", "💠"),   # 17 - Diamond with Dot
    ("5258145898612924124", "🔮"),   # 18 - Crystal Ball
    ("5260730055880876557", "🌀"),   # 19 - Cyclone
    ("5260268501515377807", "⭐"),   # 20 - Star
    ("5258093637450866522", "🦋"),   # 21 - Butterfly
    ("5258071638628377037", "✦"),   # 22 - Black Star
    ("5258362837411045098", "✧"),   # 23 - White Star
    ("5192693981456121442", "❋"),   # 24 - Heavy Eight-pointed Star
    ("5215510445460307910", "❊"),   # 25 - Eight-pointed Star
    # New emojis provided by user
    ("5202216593966244027", "📍"),   # 26 - Round Pushpin
    ("5420323339723881652", "❤️‍🔥"), # 27 - Heart on Fire
    ("5210956306952758910", "👀"),   # 28 - Eyes
    ("5224607267797606837", "🔗"),   # 29 - Link
    ("5229064374403998351", "👍"),   # 30 - Thumbs Up
    ("5240241223632954241", "😥"),   # 31 - Sad but Relieved Face
    ("5224736245665511429", "🍾"),   # 32 - Bottle with Popping Cork
    ("5197269100878907942", "✍️"),   # 33 - Writing Hand
    ("5443038326535759644", "💬"),   # 34 - Speech Balloon
    ("5443127283898405358", "📌"),   # 35 - Pushpin
    ("5444856076954520455", "🤡"),   # 36 - Clown Face
    ("5303138782004924588", "📣"),   # 37 - Megaphone
    ("5330320040883411678", "💯"),   # 38 - Hundred Points
    ("5201691993775818138", "👥"),   # 39 - Busts in Silhouette
    ("5341715473882955310", "🐻"),   # 40 - Bear Face
    ("5357069174512303778", "⛓"),   # 41 - Chains
    ("5258204546391351475", "🤖"),   # 42 - Robot
    ("5258509201306557640", "❌"),   # 43 - Cross Mark
    ("5260535596941582167", "👤"),   # 44 - Bust in Silhouette
    ("5258501105293205250", "🤬"),   # 45 - Face with Symbols on Mouth
    ("5258486128742244085", "😱"),   # 46 - Face Screaming in Fear
    # Special emojis for specific uses
    ("5321304384838057247", "🚫"),   # 47 - User Banned!
    ("5278622189556354905", "🆔"),   # 48 - ID label
    ("5210952531676504517", "⛔"),   # 49 - Banned-user notice prefix
    # Additional premium emojis provided by the user
    ("5467538555158943525", "💭"),
    ("5461117441612462242", "🙂"),
    ("5274099962655816924", "❗️"),
    ("5039780139893296083", "💰"),
    ("5332724926216428039", "📇"),
    ("5190806721286657692", "📊"),
    ("5224450179368767019", "🌎"),
    ("5303214794336125778", "🧮"),
    ("5429651785352501917", "↗️"),
    ("5429518319243775957", "📉"),
    ("5312123810638483121", "🐷"),
    ("5312441427764989435", "💱"),
    ("5379999674193172777", "🔭"),
    ("5195033767969839232", "🚀"),
    ("5262517101578443800", "🖼"),
    ("5197288647275071607", "🛡"),
    ("5291914649481007565", "💵"),
    ("5271837459783638319", "↔️"),
    ("5267102644886853973", "❤️"),
    ("5274055917766202507", "🗓"),
    ("5287231198098117669", "💰"),
    ("5278467510604160626", "💰"),
    ("5312361253610475399", "🛒"),
    ("5197434882321567830", "💵"),
    ("5445353829304387411", "💳"),
    ("5377746319601324795", "🪙"),
    ("5199552030615558774", "🪙"),
    ("5267500801240092311", "⭐"),
    ("5310278924616356636", "🎯"),
    ("5379773896352355687", "🪙"),
    ("5202113974312653146", "🪙"),
    ("5382194935057372936", "⏱"),
    ("6044307467070869456", "🚫"),   # ban admin title
    ("6043879894486618213", "🕷"),   # ban admin spider/ID
    ("6044141874606772596", "💙"),   # ban admin blue heart
    ("6046264881236153292", "🕺"),   # ban user dancer
    ("6043862633013055788", "😐"),   # ban user neutral face
    ("5978923904318573537", "👍"),   # ban user thumbs
    ("6044262726396546853", "🦋"),   # redeem butterfly
    ("6044146500286550764", "☹️"),   # redeem frown
    ("5978692057688968853", "👍"),   # broadcast thumbs
    ("6044254054857576451", "💣"),   # broadcast bomb
]

P = [E(eid, fb) for eid, fb in _EMOJI]
PREMIUM_EMOJI = {eid: E(eid, fb) for eid, fb in _EMOJI}
UKRAINE_EMOJIS = P[2]  # 💎 Diamond
ALL_CREDIT_EMOJI = PREMIUM_EMOJI["5039780139893296083"]
LE_CREDIT_EMOJI = PREMIUM_EMOJI["5039775669496579510"]


# ═══════════════════════════════════════════════════
#                 SEND HELPERS
# ═══════════════════════════════════════════════════

_EMOJI_TAG_RE = re.compile(r'<tg-emoji[^>]*>(.*?)</tg-emoji>', re.DOTALL)

def _strip_emoji_tags(text: str) -> str:
    return _EMOJI_TAG_RE.sub(r'\1', text)


def _is_emoji_parse_error(err: Exception) -> bool:
    """True only when Telegram rejected custom emoji / entity parsing."""
    s = str(err).lower()
    keys = (
        "custom emoji",
        "tg-emoji",
        "can't parse entities",
        "cant parse entities",
        "unsupported start tag",
        "unexpected end tag",
    )
    return any(k in s for k in keys)


async def rsend(target, text: str, **kw):
    kw.pop("parse_mode", None)
    try:
        msg = await target.reply_text(text, parse_mode="HTML", **kw)
    except BadRequest as e:
        if _is_emoji_parse_error(e):
            try:
                msg = await target.reply_text(_strip_emoji_tags(text), parse_mode="HTML", **kw)
            except BadRequest:
                msg = await target.reply_text(_strip_emoji_tags(text), **kw)
        else:
            try:
                msg = await target.reply_text(_strip_emoji_tags(text), parse_mode="HTML", **kw)
            except BadRequest:
                msg = await target.reply_text(_strip_emoji_tags(text), **kw)
    try:
        chat = target.chat if hasattr(target, "chat") else None
        if chat is not None and getattr(chat, "type", None) in ("group", "supergroup", "channel"):
            bot = target.get_bot() if hasattr(target, "get_bot") else None
            if bot is None and hasattr(target, "bot"):
                bot = target.bot
            if bot is not None:
                asyncio.create_task(_auto_delete_msg(bot, chat.id, msg.message_id, 60))
    except Exception:
        pass
    return msg


async def esend(msg, text: str, **kw):
    kw.pop("parse_mode", None)
    try:
        return await msg.edit_text(text, parse_mode="HTML", **kw)
    except BadRequest as e:
        if _is_emoji_parse_error(e):
            try:
                return await msg.edit_text(_strip_emoji_tags(text), parse_mode="HTML", **kw)
            except BadRequest:
                return await msg.edit_text(_strip_emoji_tags(text), **kw)
        try:
            return await msg.edit_text(_strip_emoji_tags(text), parse_mode="HTML", **kw)
        except BadRequest:
            return await msg.edit_text(_strip_emoji_tags(text), **kw)


async def bsend(bot, chat_id: int, text: str, **kw):
    kw.pop("parse_mode", None)
    try:
        msg = await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", **kw)
    except BadRequest as e:
        if _is_emoji_parse_error(e):
            try:
                msg = await bot.send_message(chat_id=chat_id, text=_strip_emoji_tags(text), parse_mode="HTML", **kw)
            except BadRequest:
                msg = await bot.send_message(chat_id=chat_id, text=_strip_emoji_tags(text), **kw)
        else:
            try:
                msg = await bot.send_message(chat_id=chat_id, text=_strip_emoji_tags(text), parse_mode="HTML", **kw)
            except BadRequest:
                msg = await bot.send_message(chat_id=chat_id, text=_strip_emoji_tags(text), **kw)
    try:
        chat = await bot.get_chat(chat_id)
        if getattr(chat, "type", None) in ("group", "supergroup", "channel"):
            asyncio.create_task(_auto_delete_msg(bot, chat_id, msg.message_id, 60))
    except Exception:
        pass
    return msg


async def _auto_delete_msg(bot, chat_id: int, message_id: int, delay: int = 60):
    try:
        await asyncio.sleep(delay)
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


def _to_bold(s: str) -> str:
    table = str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
        "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵",
    )
    return str(s).translate(table)


def _to_mono(s: str) -> str:
    table = str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
        "𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿",
    )
    return str(s).translate(table)


def style_line(label: str, value: str, emoji_idx: int = None) -> str:
    em = ""
    try:
        idx = 0 if emoji_idx is None else int(emoji_idx)
        if idx < 0:
            idx = 0
        if len(P) > 0:
            em = f"{P[idx % len(P)]} "
    except Exception:
        try:
            em = f"{P[0]} " if P else ""
        except Exception:
            em = ""
    return f"{em}[⌯] {_to_bold(label)} ⌁ {_to_mono(value)}"


def style_block(*pairs) -> str:
    lines = []
    for i, pair in enumerate(pairs):
        if not pair or len(pair) < 2:
            continue
        a, b = pair[0], pair[1]
        lines.append(style_line(str(a), str(b), emoji_idx=i % max(len(P), 1)))
    return "\n".join(lines)


def denied_block(reason: str, uid: int = None) -> str:
    lines = [
        style_line("Access", "Denied"),
        style_line("Reason", reason),
    ]
    if uid is not None:
        lines.append(style_line("Your ID", str(uid)))
    return "\n".join(lines)


# ═══════════════════════════════════════════════════
#                   DATABASE
# ═══════════════════════════════════════════════════

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username    TEXT,
            credits     INTEGER DEFAULT 5000,
            ref_code    TEXT UNIQUE,
            referred_by TEXT,
            verified    INTEGER DEFAULT 0,
            lifetime    INTEGER DEFAULT 0,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # ── Repair broken / old schema (missing telegram_id etc.) ──
    try:
        c.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in c.fetchall()}
        if cols and "telegram_id" not in cols:
            print("WARNING: users table missing telegram_id — rebuilding schema…")
            c.execute("ALTER TABLE users RENAME TO users_broken_bak")
            c.execute("""
                CREATE TABLE users (
                    telegram_id INTEGER PRIMARY KEY,
                    username    TEXT,
                    credits     INTEGER DEFAULT 5000,
                    ref_code    TEXT UNIQUE,
                    referred_by TEXT,
                    verified    INTEGER DEFAULT 0,
                    lifetime    INTEGER DEFAULT 0,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            try:
                c.execute("PRAGMA table_info(users_broken_bak)")
                old_cols = {row[1] for row in c.fetchall()}
                id_col = "id" if "id" in old_cols else ("user_id" if "user_id" in old_cols else None)
                if id_col:
                    sel_user = "username" if "username" in old_cols else "''"
                    sel_cred = "credits" if "credits" in old_cols else "5000"
                    sel_ref = "ref_code" if "ref_code" in old_cols else "NULL"
                    sel_by = "referred_by" if "referred_by" in old_cols else "NULL"
                    sel_ver = "verified" if "verified" in old_cols else "0"
                    sql = (
                        "INSERT OR IGNORE INTO users "
                        "(telegram_id, username, credits, ref_code, referred_by, verified) "
                        f"SELECT {id_col}, {sel_user}, {sel_cred}, {sel_ref}, {sel_by}, {sel_ver} "
                        "FROM users_broken_bak"
                    )
                    c.execute(sql)
            except Exception as e:
                print(f"users migrate copy skipped: {e}")
            print("users table rebuilt OK.")
    except Exception as e:
        print(f"users schema check: {e}")
    # Migration for existing DBs
    try:
        c.execute("ALTER TABLE users ADD COLUMN lifetime INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN username TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN credits INTEGER DEFAULT 5000")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN ref_code TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN referred_by TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN verified INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    except Exception:
        pass
    c.execute("""
        CREATE TABLE IF NOT EXISTS redeem_codes (
            code        TEXT PRIMARY KEY,
            credits     INTEGER NOT NULL,
            max_uses    INTEGER NOT NULL,
            used_count  INTEGER DEFAULT 0,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS redeem_uses (
            code        TEXT NOT NULL,
            telegram_id INTEGER NOT NULL,
            PRIMARY KEY (code, telegram_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS banned_users (
            telegram_id INTEGER PRIMARY KEY,
            banned_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at  TEXT,
            reason      TEXT
        )
    """)
    try:
        c.execute("ALTER TABLE banned_users ADD COLUMN expires_at TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE banned_users ADD COLUMN reason TEXT")
    except Exception:
        pass
    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_admins (
            telegram_id INTEGER PRIMARY KEY,
            added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_join_requests (
            telegram_id INTEGER NOT NULL,
            chat_id     TEXT NOT NULL DEFAULT '',
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (telegram_id, chat_id)
        )
    """)
    try:
        c.execute("PRAGMA table_info(pending_join_requests)")
        cols = {row[1] for row in c.fetchall()}
        if cols and "chat_id" not in cols:
            c.execute("ALTER TABLE pending_join_requests RENAME TO pending_join_requests_old")
            c.execute("""
                CREATE TABLE pending_join_requests (
                    telegram_id INTEGER NOT NULL,
                    chat_id     TEXT NOT NULL DEFAULT '',
                    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (telegram_id, chat_id)
                )
            """)
            try:
                c.execute(
                    "INSERT OR IGNORE INTO pending_join_requests (telegram_id, chat_id) "
                    "SELECT telegram_id, '' FROM pending_join_requests_old"
                )
            except Exception:
                pass
    except Exception:
        pass
    c.execute("""
        CREATE TABLE IF NOT EXISTS filter_keys (
            key TEXT PRIMARY KEY,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            preview TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_deliveries (
            broadcast_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            PRIMARY KEY (broadcast_id, user_id, message_id)
        )
    """)
    conn.commit()

    defaults = {
        "private_channel_id": MAIN_CHANNEL_ID,
        "main_channel_id": MAIN_CHANNEL_ID,
        "backup_channel_id": BACKUP_CHANNEL_ID,
        "third_channel_id": THIRD_CHANNEL_ID,
        "fourth_channel_id": FOURTH_CHANNEL_ID,
        "group_id": GROUP_CHAT_ID,
        # API URLs/secrets are configured privately through the owner-only Manage APIs panel.
        "api_num":     "",
        "api_tg":      "",
        "api_aadhar":  "",
        "api_vehicle": "",
        "api_pan":     "",
        "api_mobile":  "",
        "btn_num":     "1",
        "btn_tg":      "1",
        "btn_aadhar":  "1",
        "btn_refer":   "1",
        "btn_balance": "1",
        "btn_vehicle": "1",
        "btn_pan":     "1",
        "btn_mobile":  "1",
        "bot_on":      "1",
        "group_status": "0",
    }
    for key, val in defaults.items():
        c.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)", (key, val))
    # FORCE channel/group chat IDs every start
    for _k, _v in (
        ("private_channel_id", MAIN_CHANNEL_ID),
        ("main_channel_id", MAIN_CHANNEL_ID),
        ("backup_channel_id", BACKUP_CHANNEL_ID),
        ("third_channel_id", THIRD_CHANNEL_ID),
        ("fourth_channel_id", FOURTH_CHANNEL_ID),
        ("group_id", GROUP_CHAT_ID),
    ):
        c.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (_k, _v))
    conn.commit()
    conn.close()


def get_setting(key: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""


def set_setting(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def toggle_button(key: str) -> str:
    current = get_setting(key)
    new_val = "0" if current == "1" else "1"
    set_setting(key, new_val)
    return new_val


def is_bot_on() -> bool:
    return get_setting("bot_on") != "0"


def bot_status_label() -> str:
    return "ON" if is_bot_on() else "OFF"


def is_group_on() -> bool:
    return get_setting("group_status") == "1"


def group_status_label() -> str:
    return "ON" if is_group_on() else "OFF"


def is_banned(tid: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT expires_at FROM banned_users WHERE telegram_id = ?", (tid,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    expires_at = row[0]
    if expires_at:
        try:
            exp_dt = datetime.fromisoformat(expires_at)
            if datetime.utcnow() >= exp_dt:
                c.execute("DELETE FROM banned_users WHERE telegram_id = ?", (tid,))
                conn.commit()
                conn.close()
                return False
        except Exception:
            pass
    conn.close()
    return True


def ban_user(tid: int, expires_minutes: Optional[int] = None, reason: Optional[str] = None):
    if is_staff(tid):
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    expires = None
    if expires_minutes is not None and expires_minutes > 0:
        expires = (datetime.utcnow() + timedelta(minutes=expires_minutes)).isoformat()
    c.execute(
        "INSERT OR REPLACE INTO banned_users (telegram_id, banned_at, expires_at, reason) VALUES (?, CURRENT_TIMESTAMP, ?, ?)",
        (tid, expires, reason),
    )
    c.execute("UPDATE users SET credits = 0 WHERE telegram_id = ?", (tid,))
    conn.commit()
    conn.close()


def set_credits(tid: int, amount: int):
    SQLITE_MAX = 9223372036854775807
    amount = max(0, min(int(amount), SQLITE_MAX))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET credits = ? WHERE telegram_id = ?", (amount, tid))
    conn.commit()
    conn.close()


def enforce_user_credit_cap(tid: int) -> bool:
    if is_staff(tid) or is_lifetime(tid):
        return False
    cur = get_credits(tid)
    if cur <= MAX_USER_CREDITS:
        return False
    set_credits(tid, 0)
    return True


async def schedule_over_limit_refill(bot, tid: int):
    try:
        await asyncio.sleep(OVER_LIMIT_WAIT_SECONDS)
        if is_staff(tid) or is_lifetime(tid):
            return
        if get_credits(tid) == 0:
            set_credits(tid, OVER_LIMIT_REFILL_CREDITS)
            try:
                await bsend(
                    bot, tid,
                    style_block(
                        ("Bot", "Credits Restored"),
                        ("Type", "Auto Refill"),
                        ("Credits", str(OVER_LIMIT_REFILL_CREDITS)),
                        ("Limit", str(MAX_USER_CREDITS)),
                    ),
                    reply_markup=main_keyboard(),
                )
            except Exception:
                pass
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


def is_lifetime(tid: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT lifetime FROM users WHERE telegram_id = ?", (tid,))
        row = c.fetchone()
        return bool(row and row[0])
    except Exception:
        return False
    finally:
        conn.close()


def set_lifetime(tid: int, value: int = 1) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE telegram_id = ?", (tid,))
    if not c.fetchone():
        conn.close()
        return False
    c.execute("UPDATE users SET lifetime = ? WHERE telegram_id = ?", (1 if value else 0, tid))
    conn.commit()
    conn.close()
    return True


MAX_ADMIN_CREDITS = 5000
UNBAN_REFILL_CREDITS = 2000


def try_admin_add_credits(tid: int, amount: int):
    if amount <= 0:
        return False, "invalid"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT credits, COALESCE(lifetime, 0) FROM users WHERE telegram_id = ?", (tid,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "not_found"
    current, life = row
    if life:
        conn.close()
        return True, current
    new_bal = current + amount
    if not is_staff(tid) and new_bal > MAX_USER_CREDITS:
        new_bal = MAX_USER_CREDITS
    c.execute("UPDATE users SET credits = ? WHERE telegram_id = ?", (new_bal, tid))
    conn.commit()
    conn.close()
    return True, new_bal


def deduct_credits_amount(tid: int, amount: int) -> tuple:
    if amount <= 0:
        return False, get_credits(tid)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT credits, COALESCE(lifetime, 0) FROM users WHERE telegram_id = ?", (tid,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, 0
    current, life = row
    if life:
        conn.close()
        return True, current
    new_bal = max(0, current - amount)
    c.execute("UPDATE users SET credits = ? WHERE telegram_id = ?", (new_bal, tid))
    conn.commit()
    conn.close()
    return True, new_bal


def unban_user(tid: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM banned_users WHERE telegram_id = ?", (tid,))
    ok = c.rowcount > 0
    if ok:
        c.execute("UPDATE users SET credits = ? WHERE telegram_id = ?", (UNBAN_REFILL_CREDITS, tid))
    conn.commit()
    conn.close()
    return ok


def create_broadcast_log(admin_id: int, preview: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO broadcast_log (admin_id, preview) VALUES (?, ?)", (admin_id, (preview or "")[:200]))
    bid = c.lastrowid
    conn.commit()
    conn.close()
    return bid


def save_broadcast_delivery(broadcast_id: int, user_id: int, message_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO broadcast_deliveries (broadcast_id, user_id, message_id) VALUES (?, ?, ?)",
        (broadcast_id, user_id, message_id),
    )
    conn.commit()
    conn.close()


def list_broadcasts(limit: int = 20):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, admin_id, preview, created_at FROM broadcast_log ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_broadcast_deliveries(broadcast_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, message_id FROM broadcast_deliveries WHERE broadcast_id = ?", (broadcast_id,))
    rows = c.fetchall()
    conn.close()
    return rows


def delete_broadcast_log(broadcast_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM broadcast_deliveries WHERE broadcast_id = ?", (broadcast_id,))
    c.execute("DELETE FROM broadcast_log WHERE id = ?", (broadcast_id,))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════
#         PRIVATE CHANNEL JOIN REQUEST HELPERS
# ═══════════════════════════════════════════════════

def add_join_request(tid: int, chat_id: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO pending_join_requests (telegram_id, chat_id) VALUES (?, ?)",
        (tid, str(chat_id) if chat_id is not None else ""),
    )
    conn.commit()
    conn.close()


def has_join_request(tid: int, chat_id: str = None) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        if chat_id is not None and str(chat_id) != "":
            c.execute(
                "SELECT 1 FROM pending_join_requests WHERE telegram_id = ? AND chat_id = ?",
                (tid, str(chat_id)),
            )
        else:
            c.execute("SELECT 1 FROM pending_join_requests WHERE telegram_id = ?", (tid,))
        row = c.fetchone()
        return row is not None
    except Exception:
        return False
    finally:
        conn.close()


def remove_join_request(tid: int, chat_id: str = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if chat_id is not None and str(chat_id) != "":
        c.execute(
            "DELETE FROM pending_join_requests WHERE telegram_id = ? AND chat_id = ?",
            (tid, str(chat_id)),
        )
    else:
        c.execute("DELETE FROM pending_join_requests WHERE telegram_id = ?", (tid,))
    conn.commit()
    conn.close()


def _store_chat_id_from_event(chat_id, chat_type: str):
    cid = str(chat_id)
    if not cid:
        return
    ct = (chat_type or "").lower()
    if ct == "channel":
        main = get_setting("main_channel_id")
        priv = get_setting("private_channel_id")
        backup = get_setting("backup_channel_id")
        if not priv:
            set_setting("private_channel_id", cid)
        if not main:
            set_setting("main_channel_id", cid)
        elif main != cid and not backup:
            set_setting("backup_channel_id", cid)
        elif main != cid and backup and backup != cid:
            pass
        if not get_setting("private_channel_id"):
            set_setting("private_channel_id", cid)
    elif ct in ("group", "supergroup"):
        set_setting("group_id", cid)


# ═══════════════════════════════════════════════════
#         DYNAMIC FILTER KEYS
# ═══════════════════════════════════════════════════

def get_filter_keys() -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT key FROM filter_keys ORDER BY key")
        rows = c.fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def add_filter_key(key: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM filter_keys")
    count = c.fetchone()[0]
    if count >= MAX_FILTER_KEYS:
        conn.close()
        return False
    c.execute("INSERT OR IGNORE INTO filter_keys (key) VALUES (?)", (key,))
    added = c.rowcount > 0
    conn.commit()
    conn.close()
    return added


def remove_filter_key(key: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM filter_keys WHERE key = ?", (key,))
    removed = c.rowcount > 0
    conn.commit()
    conn.close()
    return removed


def _gen_ref_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def get_user(tid: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM users WHERE telegram_id = ?", (tid,))
        row = c.fetchone()
        return row
    except sqlite3.OperationalError as e:
        print(f"get_user schema error: {e}")
        try:
            conn.close()
        except Exception:
            pass
        try:
            init_db()
            conn2 = sqlite3.connect(DB_PATH)
            c2 = conn2.cursor()
            c2.execute("SELECT * FROM users WHERE telegram_id = ?", (tid,))
            row = c2.fetchone()
            conn2.close()
            return row
        except Exception as e2:
            print(f"get_user repair failed: {e2}")
            return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def create_user(tid: int, username: str, referred_by: Optional[str] = None) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    code = _gen_ref_code()
    while True:
        c.execute("SELECT 1 FROM users WHERE ref_code = ?", (code,))
        if not c.fetchone():
            break
        code = _gen_ref_code()
    c.execute(
        "INSERT OR IGNORE INTO users "
        "(telegram_id, username, credits, ref_code, referred_by, verified) "
        "VALUES (?, ?, 3000, ?, ?, 0)",
        (tid, username, code, referred_by),
    )
    conn.commit()
    referrer_tid = None
    if referred_by:
        c.execute("UPDATE users SET credits = MIN(credits + ?, ?) WHERE ref_code = ?", (REFERRAL_CREDITS, MAX_USER_CREDITS, referred_by))
        conn.commit()
        c.execute("SELECT telegram_id FROM users WHERE ref_code = ?", (referred_by,))
        row = c.fetchone()
        if row:
            referrer_tid = row[0]
    conn.close()
    return referrer_tid


def get_user_by_ref(ref_code: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE ref_code = ?", (ref_code,))
    row = c.fetchone()
    conn.close()
    return row


def set_verified(tid: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET verified = 1 WHERE telegram_id = ?", (tid,))
    conn.commit()
    conn.close()


def set_unverified(tid: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET verified = 0 WHERE telegram_id = ?", (tid,))
    conn.commit()
    conn.close()


def get_credits(tid: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE telegram_id = ?", (tid,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0


def deduct_credit(tid: int) -> bool:
    if is_lifetime(tid):
        return True
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE users SET credits = credits - 1 WHERE telegram_id = ? AND credits > 0",
        (tid,),
    )
    ok = c.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def add_credits(tid: int, amount: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE telegram_id = ?", (tid,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    new_bal = row[0] + amount
    if tid not in OWNER_IDS and tid not in ADMIN_IDS and tid not in get_dynamic_admins():
        if new_bal > MAX_USER_CREDITS:
            new_bal = MAX_USER_CREDITS
    c.execute("UPDATE users SET credits = ? WHERE telegram_id = ?", (new_bal, tid))
    conn.commit()
    conn.close()
    return True


def get_refer_count(ref_code: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (ref_code,))
    n = c.fetchone()[0]
    conn.close()
    return n


def get_all_user_ids():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users ORDER BY created_at ASC, telegram_id ASC")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_user_ids_for_credit(member_count: int) -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT telegram_id FROM users "
        "ORDER BY created_at ASC, telegram_id ASC LIMIT ?",
        (member_count,),
    )
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_stats() -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE verified = 1")
    verified_users = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(credits), 0) FROM users")
    total_credits = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE referred_by IS NOT NULL")
    total_referrals = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM redeem_codes")
    total_codes = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(used_count), 0) FROM redeem_codes")
    total_redeems = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM bot_admins")
    dynamic_admins = c.fetchone()[0]
    conn.close()
    return {
        "total_users":    total_users,
        "verified_users": verified_users,
        "total_credits":  total_credits,
        "total_referrals":total_referrals,
        "total_codes":    total_codes,
        "total_redeems":  total_redeems,
        "dynamic_admins": dynamic_admins,
    }


def create_redeem_code(credits: int, max_uses: int) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    while True:
        c.execute("SELECT 1 FROM redeem_codes WHERE code = ?", (code,))
        if not c.fetchone():
            break
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    c.execute("INSERT INTO redeem_codes (code, credits, max_uses) VALUES (?, ?, ?)", (code, credits, max_uses))
    conn.commit()
    conn.close()
    return code


def use_redeem_code(code: str, tid: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT credits, max_uses, used_count FROM redeem_codes WHERE code = ?", (code.upper(),))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "invalid"
    credits, max_uses, used_count = row
    c.execute("SELECT 1 FROM redeem_uses WHERE code = ? AND telegram_id = ?", (code.upper(), tid))
    if c.fetchone():
        conn.close()
        return False, "already_used"
    if used_count >= max_uses:
        conn.close()
        return False, "expired"
    c.execute("UPDATE redeem_codes SET used_count = used_count + 1 WHERE code = ?", (code.upper(),))
    c.execute("INSERT INTO redeem_uses (code, telegram_id) VALUES (?, ?)", (code.upper(), tid))
    c.execute("UPDATE users SET credits = credits + ? WHERE telegram_id = ?", (credits, tid))
    if tid not in OWNER_IDS and tid not in ADMIN_IDS:
        c.execute("SELECT credits FROM users WHERE telegram_id = ?", (tid,))
        row2 = c.fetchone()
        if row2 and row2[0] > MAX_USER_CREDITS:
            c.execute("UPDATE users SET credits = ? WHERE telegram_id = ?", (MAX_USER_CREDITS, tid))
    conn.commit()
    conn.close()
    return True, credits


def is_empty_api_payload(data) -> bool:
    if data is None:
        return True
    if isinstance(data, dict):
        if not data:
            return True
        if "error" in data:
            return True
        for k in ("data", "result", "results", "info", "records"):
            if k in data:
                v = data[k]
                if v in (None, "", [], {}, "null", "None"):
                    return True
                if isinstance(v, str) and not v.strip():
                    return True
        useful = {k: v for k, v in data.items() if str(k).lower() not in ("developer", "credit", "status")}
        if not useful:
            return True
        if all(v in (None, "", [], {}, "N/A", "n/a", "null", "-", "—") for v in useful.values()):
            return True
    elif isinstance(data, list) and not data:
        return True
    elif isinstance(data, str) and not data.strip():
        return True
    return False


# ═══════════════════════════════════════════════════
#              API RESPONSE CLEANER
# ═══════════════════════════════════════════════════

# ====================== TG TO NUMBER API CLEANER ======================
_REMOVE_KEYS = {
    "note",
    "developer",
    "Developer",
    "DM FOR BUY",
    "dm for buy",
    "Dm to buy access",
    "dm to buy access",
    "mr_anonymous_404.t.me",
    "key_details",
    "success",
    "status_code",
    "http_status",
    "cache",
    "cached",
    "response_time",
    "key_expiry",
    "@UsersXinfo_admin",
    "@Kon_Hu_Mai",
    "@patelkrish_99",
    "@Pro_FatherBot",
    "credit",
    "credits",
    "contact",
    "owner",
    "admin",
    "api_name",
    "powered_by",
    "Powered by",
    "Powered By",
    "poweredby",
    "key_info",
    "powered_by_store",
    "time",
    "timestamp",
    "traceid",
    "trace_id",
    "traceId",
    "version",
    "Today_Used",
    "today_used",
    "Today Used",
    "admin",
    "api_owner",
    "count",
    "credit",
    "developer",
    "group",
    "message",
}

# Filter keys (DB se lo ya direct add kar do)
def get_filter_keys() -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT key FROM filter_keys ORDER BY key")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

# Clean function (ab directly TG API ka response yahin se filter ho jayega)
def clean_api_data(data, _dynamic_keys: set = None):
    if _dynamic_keys is None:
        _dynamic_keys = set(get_filter_keys())
    all_remove = _REMOVE_KEYS | _dynamic_keys
    all_remove_lower = {str(x).lower() for x in all_remove}

    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            k_str = str(k)
            k_low = k_str.lower()
            if k_str in all_remove or k_low in all_remove_lower:
                continue
            if ("buy access" in k_low or 
                "today_used" in k_low or 
                "today used" in k_low or 
                k_low in {"powered by", "poweredby", "powered_by", "timestamp", "traceid", "trace_id", "cache", "cached", "response_time", "key_expiry"}):
                continue
            if isinstance(v, str) and (v.strip() in all_remove or v.lower().strip() in all_remove_lower):
                continue
            cleaned[k] = clean_api_data(v, _dynamic_keys)
        return cleaned
    elif isinstance(data, list):
        return [clean_api_data(item, _dynamic_keys) for item in data]
    return data


def sanitize_error_data(data):
    if isinstance(data, dict):
        if "error" in data:
            err_val = str(data["error"])
            if "HTTP Error" in err_val or "http error" in err_val.lower():
                return {"error": "No information was found."}
        return {k: sanitize_error_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_error_data(item) for item in data]
    return data


# ═══════════════════════════════════════════════════
#   BUTTON COMPAT — premium emoji + colours
# ═══════════════════════════════════════════════════

import inspect as _inspect

def _sig_has(cls, name: str) -> bool:
    try:
        return name in _inspect.signature(cls.__init__).parameters
    except Exception:
        return False


_KB_STYLE = _sig_has(KeyboardButton, "style")
_KB_ICON = _sig_has(KeyboardButton, "icon_custom_emoji_id")
_KB_APIKW = _sig_has(KeyboardButton, "api_kwargs")
_IKB_STYLE = _sig_has(InlineKeyboardButton, "style")
_IKB_ICON = _sig_has(InlineKeyboardButton, "icon_custom_emoji_id")
_IKB_APIKW = _sig_has(InlineKeyboardButton, "api_kwargs")


def KB(text: str, style: str = None, icon_custom_emoji_id: str = None, **kw):
    extra = {}
    if style is not None:
        extra["style"] = style
    if icon_custom_emoji_id is not None:
        extra["icon_custom_emoji_id"] = str(icon_custom_emoji_id)
    if extra and (_KB_STYLE or _KB_ICON):
        if _KB_STYLE and "style" in extra:
            kw["style"] = extra["style"]
        if _KB_ICON and "icon_custom_emoji_id" in extra:
            kw["icon_custom_emoji_id"] = extra["icon_custom_emoji_id"]
        try:
            return KeyboardButton(text, **kw)
        except TypeError:
            kw.pop("style", None)
            kw.pop("icon_custom_emoji_id", None)
    if extra and _KB_APIKW:
        kw["api_kwargs"] = {**(kw.get("api_kwargs") or {}), **extra}
        try:
            return KeyboardButton(text, **kw)
        except TypeError:
            kw.pop("api_kwargs", None)
    return KeyboardButton(text, **kw)


def IKB(text: str, style: str = None, icon_custom_emoji_id: str = None, **kw):
    extra = {}
    if style is not None:
        extra["style"] = style
    if icon_custom_emoji_id is not None:
        extra["icon_custom_emoji_id"] = str(icon_custom_emoji_id)
    if extra and (_IKB_STYLE or _IKB_ICON):
        if _IKB_STYLE and "style" in extra:
            kw["style"] = extra["style"]
        if _IKB_ICON and "icon_custom_emoji_id" in extra:
            kw["icon_custom_emoji_id"] = extra["icon_custom_emoji_id"]
        try:
            return InlineKeyboardButton(text, **kw)
        except TypeError:
            kw.pop("style", None)
            kw.pop("icon_custom_emoji_id", None)
    if extra and _IKB_APIKW:
        kw["api_kwargs"] = {**(kw.get("api_kwargs") or {}), **extra}
        try:
            return InlineKeyboardButton(text, **kw)
        except TypeError:
            kw.pop("api_kwargs", None)
    return InlineKeyboardButton(text, **kw)


# ═══════════════════════════════════════════════════
#                   KEYBOARDS
# ═══════════════════════════════════════════════════

async def join_keyboard(bot, uid: int, missing: dict = None) -> InlineKeyboardMarkup:
    # The initial screen shows every destination. After a failed verification,
    # show only the destinations that still need to be joined or verified.
    rows = []
    channel_group_emoji = "5156719794946311065"
    if missing is None or missing.get("need_private_channel", False):
        rows.append([IKB("JOIN CHANNEL", url=MAIN_CHANNEL_INVITE, style="primary", icon_custom_emoji_id=channel_group_emoji)])
    if missing is None or missing.get("need_public_channel", False):
        rows.append([IKB("JOIN CHANNEL", url=BACKUP_CHANNEL_INVITE, style="primary", icon_custom_emoji_id=channel_group_emoji)])
    if missing is None or missing.get("need_third_channel", False):
        rows.append([IKB("JOIN CHANNEL", url=THIRD_CHANNEL_INVITE, style="primary", icon_custom_emoji_id=channel_group_emoji)])
    if missing is None or missing.get("need_fourth_channel", False):
        rows.append([IKB("JOIN CHANNEL", url=FOURTH_CHANNEL_INVITE, style="primary", icon_custom_emoji_id=channel_group_emoji)])
    if missing is None or missing.get("need_group", False):
        rows.append([IKB("JOIN CHANNEL", url=GROUP_INVITE, style="primary", icon_custom_emoji_id=channel_group_emoji)])
    if missing is None:
        rows.append([IKB("YOUTUBE CHANNEL", url="https://youtube.com/@ukrainebst01?si=bIPSoNCI2RLp66CD", style="danger", icon_custom_emoji_id="5334681713316479679")])
    rows.append([IKB("Verify", callback_data="verify", style="primary", icon_custom_emoji_id="6044343888393539704")])
    return InlineKeyboardMarkup(rows)


def main_keyboard() -> ReplyKeyboardMarkup:
    btn_meta = {
        "Number to Info":  ("btn_num",     "primary", "5258337316715373336"),
        "Aadhar to Info":  ("btn_aadhar",  "primary", "5314504236132747481"),
        "TG to Number":    ("btn_tg",      "primary", "5406897241891824976"),
        "Refer":           ("btn_refer",   "primary", "5406897241891824976"),
        "Balance":         ("btn_balance", "primary", "6233367447789899509"),
        "Vehicle to Info": ("btn_vehicle", "primary", "5042101437237036298"),
        "PAN to Name DOB": ("btn_pan",     "primary", "5278327121008167894"),
        "Mobile Info":     ("btn_mobile",  "primary", "5443038326535759644"),
    }
    pairs = [
        ("Number to Info", "Aadhar to Info"),
        ("TG to Number", "Refer"),
        ("Balance",),
        ("Vehicle to Info", "PAN to Name DOB"),
        ("Mobile Info",),
    ]
    rows = []
    for pair in pairs:
        row = []
        for label in pair:
            key, style, eid = btn_meta[label]
            if get_setting(key) == "1":
                row.append(KB(label, style=style, icon_custom_emoji_id=eid))
        if row:
            rows.append(row)
    if not rows:
        rows = [[KB("Balance", style="primary", icon_custom_emoji_id="6233367447789899509")]]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def broadcast_stop_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[IKB("STOP BROADCAST", callback_data="broadcast_stop", style="danger", icon_custom_emoji_id="5280803324273115630")]])


def ban_admin_notice_5000(target_id: int) -> str:
    e_ban = E("6044307467070869456", "🚫")
    e_spider = E("6043879894486618213", "🕷")
    e_heart = E("6044141874606772596", "💙")
    return (
        f"{e_ban} <b>User Banned!</b>\n\n"
        f"{e_spider} ID:\n<code>{target_id}</code>\n"
        f"{e_heart} Credits set to <b>0</b>.\n"
        f"{e_ban} Ban applied by admin decision."
    )


def ban_notice_5000_text() -> str:
    e_ban = E("6044307467070869456", "🚫")
    e_dance = E("6046264881236153292", "🕺")
    e_neutral = E("6043862633013055788", "😐")
    e_thumb = E("5978923904318573537", "👍")
    return (
        f"{e_ban} <b>You have been banned.</b>\n\n"
        f"{e_dance} An admin has banned you from this bot.\n"
        f"{e_neutral} Credits have been set to <b>0</b>.\n\n"
        f"{e_thumb} Tap the button below to submit an appeal."
    )


def appeal_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [IKB(
            "Submit Appeal",
            url="https://t.me/UKRAINEBST",
            style="success",
            icon_custom_emoji_id="5278327121008167894",
        )]
    ])


def credit_review_keyboard(target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            IKB(
                "Ban",
                callback_data=f"credit_ban|{target_id}",
                style="danger",
                icon_custom_emoji_id="6044307467070869456",
            ),
            IKB(
                "Reject",
                callback_data=f"credit_reject|{target_id}",
                style="success",
                icon_custom_emoji_id="5278327121008167894",
            ),
        ]
    ])


def auto_unban_notice_text() -> str:
    e_star = E("5039775669496579510", "⭐")
    e_rocket = E("5039544445637231745", "🚀")
    e_crown = E("5042274086332400375", "👑")
    e_fire = E("5041994565565809886", "🔥")
    e_thumb = E("5978692057688968853", "👍")
    e_spark = E("5039560388555834382", "✨")
    return (
        f"{e_star} <b>Admin Action Complete</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{e_rocket} An admin has <b>unbanned</b> you!\n"
        f"{e_crown} Your access has been restored.\n"
        f"{e_fire} You received <b>{UNBAN_REFILL_CREDITS:,} Credits</b>.\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{e_thumb} Enjoy & stay within limits!\n"
        f"{e_spark} Send /start to open the menu."
    )


async def schedule_temp_unban(bot, tid: int, minutes: int = 40):
    try:
        await asyncio.sleep(minutes * 60)
        if is_banned(tid):
            unban_user(tid)
            try:
                msg = await bsend(bot, tid, auto_unban_notice_text(), reply_markup=main_keyboard())
                try:
                    await bot.pin_chat_message(
                        chat_id=tid,
                        message_id=msg.message_id,
                        disable_notification=True,
                    )
                except Exception:
                    pass
            except Exception:
                pass
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


async def notify_staff_credit_add(bot, target_id: int, amount: int, new_balance: int, source: str, extra: str = ""):
    return


def admin_panel_keyboard(uid: int) -> InlineKeyboardMarkup:
    rows = [
        [IKB("Manage Buttons", callback_data="admin_buttons", style="primary", icon_custom_emoji_id="5445059250382469069")],
        [IKB("All Credit", callback_data="admin_all_credit", style="success", icon_custom_emoji_id="5039780139893296083")],
        [IKB("Minus Credits", callback_data="admin_minus_credit", style="danger", icon_custom_emoji_id="5039614900280754969")],
        [IKB(f"Bot Status — {bot_status_label()}", callback_data="toggle_bot_status", style="primary", icon_custom_emoji_id="6321225560789877992")],
        [IKB(f"Group Status — {group_status_label()}", callback_data="toggle_group_status", style="primary", icon_custom_emoji_id="5201691993775818138")],
        [IKB("Manage Filter Keys", callback_data="admin_filter_keys", style="primary", icon_custom_emoji_id="5399885604701880145")],
        [IKB("Ban User", callback_data="admin_ban_user", style="danger", icon_custom_emoji_id="5039671744172917707"),
         IKB("Unban User", callback_data="admin_unban_user", style="success", icon_custom_emoji_id="5278327121008167894")],
        [IKB("Remove Old Broadcast", callback_data="admin_remove_broadcast", style="danger", icon_custom_emoji_id="6044254054857576451")],
    ]
    if is_owner(uid):
        rows.insert(1, [IKB("Manage APIs", callback_data="admin_apis", style="primary", icon_custom_emoji_id="5042101437237036298")])
        rows.insert(2, [IKB("Add Admin", callback_data="admin_add_admin", style="success", icon_custom_emoji_id="5278327121008167894"),
                        IKB("Remove Admin", callback_data="admin_remove_admin", style="danger", icon_custom_emoji_id="5039614900280754969")])
        rows.append([IKB("Download bot.db", callback_data="admin_download_db", style="success", icon_custom_emoji_id="5330320040883411678")])
    return InlineKeyboardMarkup(rows)


def buttons_manage_keyboard() -> InlineKeyboardMarkup:
    def state(key):
        return "ON" if get_setting(key) == "1" else "OFF"

    def style_for(key):
        return "success" if get_setting(key) == "1" else "danger"

    return InlineKeyboardMarkup([
        [IKB(
            f"Number to Info — {state('btn_num')}",
            callback_data="toggle_btn_num",
            style=style_for("btn_num"),
            icon_custom_emoji_id="5258337316715373336",
        )],
        [IKB(
            f"TG to Number — {state('btn_tg')}",
            callback_data="toggle_btn_tg",
            style=style_for("btn_tg"),
            icon_custom_emoji_id="5406897241891824976",
        )],
        [IKB(
            f"Aadhar to Info — {state('btn_aadhar')}",
            callback_data="toggle_btn_aadhar",
            style=style_for("btn_aadhar"),
            icon_custom_emoji_id="5314504236132747481",
        )],
        [IKB(
            f"Vehicle to Info — {state('btn_vehicle')}",
            callback_data="toggle_btn_vehicle",
            style=style_for("btn_vehicle"),
            icon_custom_emoji_id="5042101437237036298",
        )],
        [IKB(
            f"PAN to Name DOB — {state('btn_pan')}",
            callback_data="toggle_btn_pan",
            style=style_for("btn_pan"),
            icon_custom_emoji_id="5278327121008167894",
        )],
        [IKB(
            f"Mobile Info — {state('btn_mobile')}",
            callback_data="toggle_btn_mobile",
            style=style_for("btn_mobile"),
            icon_custom_emoji_id="5443038326535759644",
        )],
        [IKB(
            f"Refer — {state('btn_refer')}",
            callback_data="toggle_btn_refer",
            style=style_for("btn_refer"),
            icon_custom_emoji_id="5406897241891824976",
        )],
        [IKB(
            f"Balance — {state('btn_balance')}",
            callback_data="toggle_btn_balance",
            style=style_for("btn_balance"),
            icon_custom_emoji_id="6233367447789899509",
        )],
        [IKB(
            "Back",
            callback_data="back_admin",
            style="primary",
            icon_custom_emoji_id="5445365692004071819",
        )],
    ])


def filter_keys_keyboard() -> InlineKeyboardMarkup:
    rows = []
    keys = get_filter_keys()
    for k in keys:
        rows.append([
            IKB(
                f"🗑 {k}",
                callback_data=f"fk_del|{k}",
                style="danger",
                icon_custom_emoji_id="5039614900280754969",
            )
        ])
    rows.append([
        IKB(
            "Add New Key",
            callback_data="fk_add",
            style="success",
            icon_custom_emoji_id="5278327121008167894",
        )
    ])
    rows.append([
        IKB(
            "Back",
            callback_data="back_admin",
            style="primary",
            icon_custom_emoji_id="5445365692004071819",
        )
    ])
    return InlineKeyboardMarkup(rows)


def apis_manage_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [IKB("✏️ Number Info API", callback_data="edit_api_num"),
         IKB("🗑 Delete", callback_data="delete_api_num")],
        [IKB("✏️ TG to Number API", callback_data="edit_api_tg"),
         IKB("🗑 Delete", callback_data="delete_api_tg")],
        [IKB("✏️ Aadhar Info API", callback_data="edit_api_aadhar"),
         IKB("🗑 Delete", callback_data="delete_api_aadhar")],
        [IKB("✏️ Vehicle to Info API", callback_data="edit_api_vehicle"),
         IKB("🗑 Delete", callback_data="delete_api_vehicle")],
        [IKB("✏️ PAN to Name DOB API", callback_data="edit_api_pan"),
         IKB("🗑 Delete", callback_data="delete_api_pan")],
        [IKB("✏️ Mobile Info API", callback_data="edit_api_mobile"),
         IKB("🗑 Delete", callback_data="delete_api_mobile")],
        [IKB("Back", callback_data="back_admin", style="primary", icon_custom_emoji_id="5445365692004071819")],
    ])


# ═══════════════════════════════════════════════════
#              MEMBERSHIP CHECK
# ═══════════════════════════════════════════════════

async def _check_chat_member(bot, chat_ref, uid: int):
    if not chat_ref:
        return None
    try:
        ref = int(chat_ref) if str(chat_ref).lstrip("-").isdigit() else chat_ref
        m = await bot.get_chat_member(ref, uid)
        status = getattr(m, "status", None)
        status_str = str(status).lower() if status is not None else ""
        if status_str in ("left", "kicked", "banned", "chatmemberstatus.left",
                          "chatmemberstatus.kicked", "chatmemberstatus.banned"):
            return False
        if "left" in status_str or "kicked" in status_str or "banned" in status_str:
            return False
        return True
    except Exception as e:
        try:
            print(f"get_chat_member fail chat={chat_ref} uid={uid}: {type(e).__name__}: {e}")
        except Exception:
            pass
        return None


async def _chat_requirement(bot, uid: int, chat_id_setting: str) -> bool:
    cid = (chat_id_setting or "").strip()
    if not cid:
        return True
    ok = await _check_chat_member(bot, cid, uid)
    if ok is True:
        return False
    if ok is False:
        return True
    if has_join_request(uid, cid):
        return False
    return True


async def get_membership_status(bot, uid: int) -> dict:
    main_id = get_setting("main_channel_id") or get_setting("private_channel_id") or MAIN_CHANNEL_ID
    backup_id = get_setting("backup_channel_id") or BACKUP_CHANNEL_ID
    group_id = get_setting("group_id") or GROUP_CHAT_ID
    third_id = get_setting("third_channel_id")
    fourth_id = get_setting("fourth_channel_id") or FOURTH_CHANNEL_ID

    need_private = await _chat_requirement(bot, uid, main_id)
    if need_private and CHANNEL_USERNAME.startswith("@"):
        need_private = await _chat_requirement(bot, uid, CHANNEL_USERNAME)

    need_public = await _chat_requirement(bot, uid, backup_id)
    if need_public and CHANNEL_USERNAME2.startswith("@"):
        need_public = await _chat_requirement(bot, uid, CHANNEL_USERNAME2)

    need_group = await _chat_requirement(bot, uid, group_id)
    # Channel 3 passes if Telegram confirms membership OR this bot recorded the join request.
    # This also supports users who joined before the bot was configured with the channel ID.
    third_member_ok = await _check_chat_member(bot, third_id, uid) if third_id else False
    need_third_request = (not bool(third_id)) or not (third_member_ok is True or has_join_request(uid, third_id))
    need_fourth = await _chat_requirement(bot, uid, fourth_id)

    return {
        "need_private_channel": need_private,
        "need_public_channel": need_public,
        "need_group": need_group,
        "need_third_channel": need_third_request,
        "need_fourth_channel": need_fourth,
    }


async def is_member(bot, uid: int) -> bool:
    try:
        st = await get_membership_status(bot, uid)
        if st.get("need_private_channel") or st.get("need_public_channel") or st.get("need_group") or st.get("need_third_channel") or st.get("need_fourth_channel"):
            return False
        return True
    except Exception:
        return False


def is_private(update: Update) -> bool:
    return update.effective_chat.type == "private"


def is_group_chat(update: Update) -> bool:
    return update.effective_chat.type in ("group", "supergroup")


# ═══════════════════════════════════════════════════
#            LOADING ANIMATION
# ═══════════════════════════════════════════════════

FRAMES = [
    ("[ ■■■■■■■■■■ ]", "100%"),
]
FRAME_DELAY = 0.0


async def run_loading_animation(prog_msg, label: str = "Searching database"):
    try:
        await esend(
            prog_msg,
            style_block(
                ("System", "Searching"),
                ("Status", label),
            ),
        )
    except Exception:
        pass


# ═══════════════════════════════════════════════════
#                   HANDLERS
# ═══════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return
    user = update.effective_user

    if not is_staff(user.id) and not is_bot_on():
        await rsend(
            update.message,
            style_block(
                ("Bot", "Paused"),
                ("Status", "Maintenance"),
                ("Type", "Please try later"),
            ),
        )
        return

    args = ctx.args or []

    referred_by = None
    if args and args[0].startswith("ref_"):
        code = args[0][4:]
        referrer = get_user_by_ref(code)
        if referrer and referrer[0] != user.id:
            referred_by = code

    referrer_tid = None
    if not get_user(user.id):
        referrer_tid = create_user(user.id, user.username or user.first_name, referred_by)

    if referrer_tid:
        new_credits = get_credits(referrer_tid)
        try:
            await bsend(
                ctx.bot, referrer_tid,
                style_block(
                    ("Bot", "Referral"),
                    ("Type", "Complete"),
                    ("Reward", f"+{REFERRAL_CREDITS} Credits"),
                    ("Balance", f"{new_credits} Credits"),
                    ("Tip", "Keep sharing your link"),
                ),
            )
        except Exception:
            pass

    db_user = get_user(user.id)
    if db_user and db_user[5] == 1:
        if not is_staff(user.id) and enforce_user_credit_cap(user.id):
            await rsend(
                update.message,
                style_block(
                    ("Bot", "Credits Reset"),
                    ("Type", "Over Limit"),
                    ("Balance", "0"),
                    ("Refill", f"{OVER_LIMIT_REFILL_CREDITS} in 1 hour"),
                ),
                reply_markup=main_keyboard(),
            )
            asyncio.create_task(schedule_over_limit_refill(ctx.bot, user.id))
            return
        await rsend(
            update.message,
            style_block(
                ("Bot", "Verified"),
                ("Type", "Already Verified"),
                ("Status", "Ready to use"),
            ) + "\n\n"
            + f"{P[10]} 𝙲𝚑𝚘𝚘𝚜𝚎 𝚊𝚗 𝚘𝚙𝚝𝚒𝚘𝚗 𝚏𝚛𝚘𝚖 𝚝𝚑𝚎 𝚖𝚎𝚗𝚞 𝚋𝚎𝚕𝚘𝚠.",
            reply_markup=main_keyboard(),
        )
        return

    kb = await join_keyboard(ctx.bot, user.id)
    await rsend(
        update.message,
        style_block(
            ("Bot", "UKRAINEBST"),
            ("Type", "Welcome"),
            ("Step 1", "Join Channel"),
            ("Step 2", "Join Group"),
            ("Step 3", "Tap Verify"),
        ) + "\n\n"
        + f"{P[25]} Click the buttons below to proceed:",
        reply_markup=kb,
    )


async def cb_verify(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    # Check each required destination so the user can see exactly what is missing.
    try:
        status = await get_membership_status(ctx.bot, user.id)
        member_ok = not any(status.values())
    except Exception:
        status = {
            "need_private_channel": True,
            "need_public_channel": True,
            "need_group": True,
            "need_third_channel": True,
            "need_fourth_channel": True,
        }
        member_ok = False

    if not member_ok:
        labels = {
            "need_private_channel": "Main Channel",
            "need_public_channel": "Backup Channel",
            "need_third_channel": "Channel 3 (join request required)",
            "need_fourth_channel": "New Channel",
            "need_group": "Group",
        }
        missing_names = [name for key, name in labels.items() if status.get(key)]
        message = (
            style_block(
                ("Verification", "Incomplete"),
                ("Not Joined / Not Confirmed", ", ".join(missing_names) or "Required destinations"),
                ("Next Step", "Join the destination shown below, then tap Verify again."),
            )
        )
        try:
            await query.answer(
                "Please join or complete the join request for: " + ", ".join(missing_names),
                show_alert=True,
            )
        except Exception:
            pass
        try:
            await query.message.edit_text(
                message,
                parse_mode="HTML",
                reply_markup=await join_keyboard(ctx.bot, user.id, missing=status),
            )
        except Exception:
            try:
                await query.message.edit_reply_markup(
                    reply_markup=await join_keyboard(ctx.bot, user.id, missing=status)
                )
            except Exception:
                pass
        return

    await query.answer("Membership verified!", show_alert=False)

    try:
        add_join_request(user.id)
    except Exception:
        pass

    set_verified(user.id)
    try:
        await query.message.delete()
    except Exception:
        pass

    credits = get_credits(user.id)
    first = html.escape(user.first_name)
    await bsend(
        ctx.bot, user.id,
        style_block(
            ("Bot", "Verification"),
            ("Type", "Successful"),
            ("User", first),
            ("Credits", str(credits)),
            ("Status", "Ready"),
        ) + f"\n\n{P[10]} 𝙲𝚑𝚘𝚘𝚜𝚎 𝚊𝚗 𝚘𝚙𝚝𝚒𝚘𝚗 𝚏𝚛𝚘𝚖 𝚝𝚑𝚎 𝚖𝚎𝚗𝚞 𝚋𝚎𝚕𝚘𝚠.",
        reply_markup=main_keyboard(),
    )


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    in_private = is_private(update)
    in_group   = is_group_chat(update)

    if not in_private:
        if not in_group or not is_group_on():
            return

    user = update.effective_user
    text = update.message.text.strip()

    if in_group:
        clean_check = text.replace("⭐","").replace("📱","").replace("👥","").replace("💰","").strip()
        valid_cmds = [
            "Number to Info", "TG to Number", "Aadhar to Info",
            "Vehicle to Info", "PAN to Name DOB", "Refer", "Balance", "Mobile Info"
        ]
        pending_admin_input = is_staff(user.id) and any(
            ctx.user_data.get(key)
            for key in (
                "waiting_ban_id",
                "waiting_unban_id",
                "waiting_all_credit_count",
                "waiting_all_credit_amount",
                "waiting_add_admin_id",
                "waiting_remove_admin_id",
                "waiting_minus_id",
                "waiting_minus_amount",
            )
        )
        if not pending_admin_input and not any(cmd in clean_check for cmd in valid_cmds):
            return

    db_user = get_user(user.id)
    if not db_user or db_user[5] != 1:
        if in_private:
            kb = await join_keyboard(ctx.bot, user.id)
            await rsend(
                update.message,
                style_block(
                    ("Bot", "Access Denied"),
                    ("Type", "Not Verified"),
                    ("Action", "Send /start"),
                    ("Step", "Join and Verify"),
                ),
                reply_markup=kb,
            )
        return

    if not await is_member(ctx.bot, user.id):
        set_unverified(user.id)
        if in_private:
            kb = await join_keyboard(ctx.bot, user.id)
            await rsend(
                update.message,
                style_block(
                    ("Bot", "Access Revoked"),
                    ("Type", "Left Channel or Group"),
                    ("Action", "Join again"),
                    ("Step", "Then Verify"),
                ),
                reply_markup=kb,
            )
        else:
            bot_me = await ctx.bot.get_me()
            await rsend(
                update.message,
                style_block(
                    ("Bot", "Access Revoked"),
                    ("Type", "Join required"),
                    ("Action", "Open private chat"),
                    ("Bot", f"@{bot_me.username}"),
                ),
            )
        return

    if is_staff(user.id) and ctx.user_data.get("waiting_fk_add"):
        await receive_filter_key(update, ctx)
        return

    if is_staff(user.id) and ctx.user_data.get("waiting_ban_id"):
        await process_ban_id(update, ctx, text)
        return

    if is_staff(user.id) and ctx.user_data.get("waiting_unban_id"):
        await process_unban_id(update, ctx, text)
        return

    if is_staff(user.id) and ctx.user_data.get("waiting_all_credit_count"):
        await process_all_credit_count(update, ctx, text)
        return

    if is_staff(user.id) and ctx.user_data.get("waiting_all_credit_amount"):
        await process_all_credit_amount(update, ctx, text)
        return

    if is_owner(user.id) and ctx.user_data.get("waiting_add_admin_id"):
        await process_add_admin_id(update, ctx, text)
        return

    if is_owner(user.id) and ctx.user_data.get("waiting_remove_admin_id"):
        await process_remove_admin_id(update, ctx, text)
        return

    if is_staff(user.id) and ctx.user_data.get("waiting_minus_id"):
        await process_minus_id(update, ctx, text)
        return

    if is_staff(user.id) and ctx.user_data.get("waiting_minus_amount"):
        await process_minus_amount(update, ctx, text)
        return

    if not is_staff(user.id) and is_banned(user.id):
        await rsend(
            update.message,
            style_block(
                ("Bot", "Banned"),
                ("Type", "Access Blocked"),
                ("Status", "Contact support"),
            ),
        )
        return

    if not is_staff(user.id) and not is_bot_on():
        await rsend(
            update.message,
            style_block(
                ("Bot", "Paused"),
                ("Status", "Maintenance"),
                ("Type", "Please try later"),
            ),
        )
        return

    clean = text.replace("⭐", "").replace("📱", "").replace("👥", "").replace("💰", "").strip()

    if "Number to Info" in clean:
        await start_num_info(update, ctx)
    elif "TG to Number" in clean:
        await start_tg_info(update, ctx)
    elif "Aadhar to Info" in clean:
        await start_aadhar_info(update, ctx)
    elif "Vehicle to Info" in clean:
        await start_vehicle_info(update, ctx)
    elif "PAN to Name DOB" in clean:
        await start_pan_info(update, ctx)
    elif "Mobile Info" in clean:
        await start_mobile_info(update, ctx)
    elif "Refer" in clean and "Number" not in clean:
        await show_refer(update, ctx)
    elif "Balance" in clean:
        await show_balance(update, ctx)
    elif ctx.user_data.get("waiting_api_edit") and is_owner(user.id):
        await receive_api_value(update, ctx)
    elif ctx.user_data.get("waiting_number"):
        await process_number(update, ctx, text)
    elif ctx.user_data.get("waiting_tg"):
        await process_tg_username(update, ctx, text)
    elif ctx.user_data.get("waiting_aadhar"):
        await process_aadhar(update, ctx, text)
    elif ctx.user_data.get("waiting_vehicle"):
        await process_vehicle(update, ctx, text)
    elif ctx.user_data.get("waiting_pan"):
        await process_pan_info(update, ctx, text)
    elif ctx.user_data.get("waiting_mobile"):
        await process_mobile(update, ctx, text)
    elif in_private:
        await rsend(
            update.message,
            style_block(
                ("Bot", "Menu"),
                ("Type", "Choose Option"),
                ("Status", "Use buttons below"),
            ),
            reply_markup=main_keyboard(),
        )


# ═══════════════════════════════════════════════════
#              AUTO CREDIT TOP-UP
# ═══════════════════════════════════════════════════

async def check_and_auto_topup(bot, uid: int):
    if get_credits(uid) <= 0 and not is_lifetime(uid):
        add_credits(uid, 50)
        new_bal = get_credits(uid)
        try:
            await bsend(
                bot, uid,
                style_block(
                    ("Bot", "Auto Topup"),
                    ("Type", "Credits Restored"),
                    ("Added", "50 FREE Credits"),
                    ("Balance", str(new_bal)),
                ),
            )
        except Exception:
            pass


# ─── Number to Info ───────────────────────────────

async def start_num_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    credits = get_credits(uid)
    await rsend(
        update.message,
        style_block(
            ("Bot", "Number to Info"),
            ("Type", "UKRAINEBST Premium Number to Info"),
            ("Balance", f"{credits} Credits"),
            ("Charge", "1 Credit"),
            ("Input", "10 digit number"),
            ("Example", "6205923286"),
        ),
    )
    ctx.user_data["waiting_number"]  = True
    ctx.user_data["waiting_pan"]      = False
    ctx.user_data["waiting_tg"]      = False
    ctx.user_data["waiting_aadhar"]  = False
    ctx.user_data["waiting_vehicle"] = False
    ctx.user_data["waiting_mobile"]  = False


async def process_number(update: Update, ctx: ContextTypes.DEFAULT_TYPE, number: str):
    uid = update.effective_user.id
    number = number.strip()

    if not number.isdigit() or len(number) != 10:
        await rsend(
            update.message,
            style_block(
                ("Bot", "Number to Info"),
                ("Type", "Invalid Number"),
                ("Need", "10 digit number"),
                ("Example", "6205923286"),
            ),
        )
        return

    ctx.user_data["waiting_number"] = False

    if get_credits(uid) <= 0 and not is_lifetime(uid):
        await rsend(
            update.message,
            style_block(
                ("Bot", "Credits"),
                ("Type", "Insufficient Credits"),
                ("Action", "Refer friends"),
                ("Reward", "+1 Credit per referral"),
            ),
            reply_markup=main_keyboard(),
        )
        return

    prog = await rsend(
        update.message,
        style_block(
            ("System", "Searching"),
            ("Status", "Searching database"),
            ("Number", number),
        ),
    )

    await run_loading_animation(prog, "Searching database")

    api_template = get_setting("api_num")
    api_url = api_template.replace("{num}", number)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                data = await resp.json(content_type=None)
    except Exception as e:
        await esend(
            prog,
            style_block(
                ("Bot", "API Error"),
                ("Type", "Request Failed"),
                ("Detail", str(e)[:80]),
            ),
        )
        return

    data = clean_api_data(data)
    data = sanitize_error_data(data)

    if is_empty_api_payload(data):
        await esend(
            prog,
            style_block(
                ("Bot", "Number to Info"),
                ("Type", "No Data Found"),
                ("Status", "No information found"),
            ),
        )
        return

    deduct_credit(uid)
    remaining = get_credits(uid)
    if remaining <= 0:
        await check_and_auto_topup(ctx.bot, uid)
        remaining = get_credits(uid)
    json_text = html.escape(json.dumps(data, indent=2, ensure_ascii=False))

    result = (
        style_block(
            ("Bot", "Number to Info"),
            ("Type", "Result Found"),
            ("Credits", str(remaining)),
        ) + f"\n\n<pre><code>{json_text}</code></pre>\n\n"
        + f'{P[2]} [⌯] {_to_bold("API BUY")} ⌁ <a href="http://t.me/UKRAINEBST">{_to_mono("UKRAINEBST")}</a>'
    )
    try:
        await esend(prog, result)
    except Exception:
        await rsend(update.message, result)


# ─── TG to Number ─────────────────────────────────

async def start_tg_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    credits = get_credits(uid)
    await rsend(
        update.message,
        style_block(
            ("Bot", "TG to Number"),
            ("Type", "Premium TG to Number"),
            ("Balance", f"{credits} Credits"),
            ("Charge", "1 Credit"),
            ("Input", "Chat ID or @username"),
            ("Example", "5678901234"),
        ),
    )
    ctx.user_data["waiting_tg"]      = True
    ctx.user_data["waiting_pan"]      = False
    ctx.user_data["waiting_number"]  = False
    ctx.user_data["waiting_aadhar"]  = False
    ctx.user_data["waiting_vehicle"] = False
    ctx.user_data["waiting_mobile"]  = False


async def process_tg_username(update: Update, ctx: ContextTypes.DEFAULT_TYPE, chat_id: str):
    uid = update.effective_user.id
    chat_id = chat_id.strip().lstrip("@")

    ctx.user_data["waiting_tg"] = False

    is_numeric = chat_id.lstrip("-").isdigit()
    is_username = bool(re.match(r"^[A-Za-z0-9_]{4,32}$", chat_id))
    if not is_numeric and not is_username:
        await rsend(
            update.message,
            style_block(
                ("Bot", "TG to Number"),
                ("Type", "Invalid Input"),
                ("Need", "Chat ID or username"),
                ("Example", "5678901234"),
            ),
        )
        return

    if get_credits(uid) <= 0 and not is_lifetime(uid):
        await rsend(
            update.message,
            style_block(
                ("Bot", "Credits"),
                ("Type", "Insufficient Credits"),
                ("Action", "Refer friends"),
                ("Reward", "+1 Credit per referral"),
            ),
            reply_markup=main_keyboard(),
        )
        return

    prog = await rsend(
        update.message,
        style_block(
            ("System", "Searching"),
            ("Status", "Searching database"),
            ("Query", chat_id),
        ),
    )

    await run_loading_animation(prog, "Searching database")

    api_template = get_setting("api_tg")
    api_url1 = ""
    if api_template:
        api_url1 = (
            api_template
            .replace("{chatid}", chat_id)
            .replace("{num}", chat_id)
            .replace("{TELEGRAM_ID_OR_USERNAME}", chat_id)
            .replace("{id}", chat_id)
        )

    data = {}
    api_error = None
    try:
        async with aiohttp.ClientSession() as session:
            for api_url in (api_url1,):
                if not api_url:
                    continue
                try:
                    async with session.get(
                        api_url,
                        timeout=aiohttp.ClientTimeout(total=12),
                        headers={"Accept": "application/json"},
                    ) as resp:
                        raw_body = await resp.text()
                        if resp.status >= 400 or not raw_body.strip():
                            api_error = f"HTTP {resp.status}"
                            continue
                        try:
                            payload = json.loads(raw_body)
                        except json.JSONDecodeError:
                            api_error = "The API returned an invalid response."
                            continue
                        if isinstance(payload, dict) and payload.get("success") is False:
                            api_error = str(payload.get("msg") or payload.get("error") or "No result")
                            continue
                        if isinstance(payload, dict) and isinstance(data, dict):
                            data.update({key: value for key, value in payload.items() if key not in data})
                        elif not data and payload:
                            data = payload
                        if isinstance(payload, dict) and (
                            payload.get("number") or payload.get("phone") or payload.get("mobile")
                        ):
                            break
                except Exception as exc:
                    api_error = str(exc)
                    continue
    except Exception as exc:
        await esend(
            prog,
            style_block(
                ("Bot", "API Error"),
                ("Type", "Request Failed"),
                ("Detail", str(exc)[:80]),
            ),
        )
        return

    data = clean_api_data(data)
    data = sanitize_error_data(data)

    if not data or (isinstance(data, dict) and "error" in data):
        await esend(
            prog,
            style_block(
                ("Bot", "TG to Number"),
                ("Type", "No Result"),
                ("Status", "No number was found"),
            ),
        )
        return

    deduct_credit(uid)
    remaining = get_credits(uid)
    if remaining <= 0:
        await check_and_auto_topup(ctx.bot, uid)
        remaining = get_credits(uid)
    json_text = html.escape(json.dumps(data, indent=2, ensure_ascii=False))

    result = (
        style_block(
            ("Bot", "TG to Number"),
            ("Type", "Result Found"),
            ("Credits", str(remaining)),
        ) + f"\n\n<pre><code>{json_text}</code></pre>\n\n"
        + f'{P[2]} [⌯] {_to_bold("API BUY")} ⌁ <a href="http://t.me/UKRAINEBST">{_to_mono("UKRAINEBST")}</a>'
    )
    try:
        await esend(prog, result)
    except Exception:
        await rsend(update.message, result)


# ─── Aadhar to Info ───────────────────────────────

async def start_aadhar_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    credits = get_credits(uid)
    await rsend(
        update.message,
        style_block(
            ("Bot", "Aadhar to Info"),
            ("Type", "Premium Aadhar to Info"),
            ("Balance", f"{credits} Credits"),
            ("Charge", "1 Credit"),
            ("Input", "12 digit Aadhar"),
            ("Example", "327567544017"),
        ),
    )
    ctx.user_data["waiting_aadhar"]  = True
    ctx.user_data["waiting_pan"]      = False
    ctx.user_data["waiting_number"]  = False
    ctx.user_data["waiting_tg"]      = False
    ctx.user_data["waiting_vehicle"] = False
    ctx.user_data["waiting_mobile"]  = False


async def process_aadhar(update: Update, ctx: ContextTypes.DEFAULT_TYPE, aadhar: str):
    uid = update.effective_user.id
    aadhar = aadhar.strip().replace(" ", "")

    if not aadhar.isdigit() or len(aadhar) != 12:
        await rsend(
            update.message,
            style_block(
                ("Bot", "Aadhar to Info"),
                ("Type", "Invalid Aadhar"),
                ("Need", "12 digit Aadhar"),
                ("Example", "327567544017"),
            ),
        )
        return

    ctx.user_data["waiting_aadhar"] = False

    if get_credits(uid) <= 0 and not is_lifetime(uid):
        await rsend(
            update.message,
            style_block(
                ("Bot", "Credits"),
                ("Type", "Insufficient Credits"),
                ("Action", "Refer friends"),
                ("Reward", "+1 Credit per referral"),
            ),
            reply_markup=main_keyboard(),
        )
        return

    prog = await rsend(
        update.message,
        style_block(
            ("System", "Searching"),
            ("Status", "Searching database"),
        ),
    )

    await run_loading_animation(prog, "Searching database")

    api_template = get_setting("api_aadhar")
    api_url = api_template.replace("{id}", aadhar)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                data = await resp.json(content_type=None)
    except Exception as e:
        await esend(
            prog,
            style_block(
                ("Bot", "API Error"),
                ("Type", "Request Failed"),
                ("Detail", str(e)[:80]),
            ),
        )
        return

    data = clean_api_data(data)
    data = sanitize_error_data(data)
    deduct_credit(uid)
    remaining = get_credits(uid)
    if remaining <= 0:
        await check_and_auto_topup(ctx.bot, uid)
        remaining = get_credits(uid)
    json_text = html.escape(json.dumps(data, indent=2, ensure_ascii=False))

    result = (
        style_block(
            ("Bot", "Aadhar to Info"),
            ("Type", "Result Found"),
            ("Credits", str(remaining)),
        ) + f"\n\n<pre><code>{json_text}</code></pre>\n\n"
        + f'{P[2]} [⌯] {_to_bold("API BUY")} ⌁ <a href="http://t.me/UKRAINEBST">{_to_mono("UKRAINEBST")}</a>'
    )
    try:
        await esend(prog, result)
    except Exception:
        await rsend(update.message, result)


# ─── Vehicle to Info ──────────────────────────────

async def start_vehicle_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    credits = get_credits(uid)
    await rsend(
        update.message,
        style_block(
            ("Bot", "Vehicle to Info"),
            ("Type", "Premium Vehicle to Info"),
            ("Balance", f"{credits} Credits"),
            ("Charge", "1 Credit"),
            ("Input", "Registration Number"),
            ("Example", "MH12AB1234"),
        ),
    )
    ctx.user_data["waiting_vehicle"] = True
    ctx.user_data["waiting_pan"]      = False
    ctx.user_data["waiting_number"]  = False
    ctx.user_data["waiting_tg"]      = False
    ctx.user_data["waiting_aadhar"]  = False
    ctx.user_data["waiting_mobile"]  = False


async def process_vehicle(update: Update, ctx: ContextTypes.DEFAULT_TYPE, plate: str):
    uid = update.effective_user.id
    plate = plate.strip().upper().replace(" ", "")

    if len(plate) < 4:
        await rsend(
            update.message,
            style_block(
                ("Bot", "Vehicle to Info"),
                ("Type", "Invalid Number"),
                ("Need", "Registration number"),
                ("Example", "MH12AB1234"),
            ),
        )
        return

    ctx.user_data["waiting_vehicle"] = False

    if get_credits(uid) <= 0 and not is_lifetime(uid):
        await rsend(
            update.message,
            style_block(
                ("Bot", "Credits"),
                ("Type", "Insufficient Credits"),
                ("Action", "Refer friends"),
                ("Reward", "+1 Credit per referral"),
            ),
            reply_markup=main_keyboard(),
        )
        return

    prog = await rsend(
        update.message,
        style_block(
            ("System", "Searching"),
            ("Status", "Fetching vehicle data"),
        ),
    )

    await run_loading_animation(prog, "Fetching vehicle data")

    api_template = get_setting("api_vehicle")
    api_url = api_template.replace("{vehicle}", plate)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                data = await resp.json(content_type=None)
    except Exception as e:
        await esend(
            prog,
            style_block(
                ("Bot", "API Error"),
                ("Type", "Request Failed"),
                ("Detail", str(e)[:80]),
            ),
        )
        return

    data = clean_api_data(data)
    data = sanitize_error_data(data)
    deduct_credit(uid)
    remaining = get_credits(uid)
    if remaining <= 0:
        await check_and_auto_topup(ctx.bot, uid)
        remaining = get_credits(uid)
    json_text = html.escape(json.dumps(data, indent=2, ensure_ascii=False))

    result = (
        style_block(
            ("Bot", "Vehicle to Info"),
            ("Type", "Result Found"),
            ("Credits", str(remaining)),
        ) + f"\n\n<pre><code>{json_text}</code></pre>\n\n"
        + f'{P[2]} [⌯] {_to_bold("API BUY")} ⌁ <a href="http://t.me/UKRAINEBST">{_to_mono("UKRAINEBST")}</a>'
    )
    try:
        await esend(prog, result)
    except Exception:
        await rsend(update.message, result)



# ─── PAN to Name DOB ──────────────────────────────
# This feature requires the owner's own authorized PAN API.
# The endpoint is configured from the Admin > Manage APIs panel as api_pan.

async def start_pan_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    credits = get_credits(uid)
    await rsend(
        update.message,
        style_block(
            ("Bot", "PAN to Name DOB"),
            ("Type", "Authorized PAN Lookup"),
            ("Balance", f"{credits} Credits"),
            ("Charge", "1 Credit"),
            ("Input", "PAN Number"),
            ("Example", "ABCDE1234F"),
        ),
    )
    ctx.user_data["waiting_pan"] = True
    ctx.user_data["waiting_number"] = False
    ctx.user_data["waiting_tg"] = False
    ctx.user_data["waiting_aadhar"] = False
    ctx.user_data["waiting_vehicle"] = False
    ctx.user_data["waiting_mobile"] = False


async def process_pan_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE, pan: str):
    uid = update.effective_user.id
    pan = pan.strip().upper().replace(" ", "")

    if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan):
        await rsend(
            update.message,
            style_block(
                ("Bot", "PAN to Name DOB"),
                ("Type", "Invalid PAN"),
                ("Format", "ABCDE1234F"),
            ),
        )
        return

    ctx.user_data["waiting_pan"] = False
    api_template = get_setting("api_pan").strip()

    if not api_template:
        await rsend(
            update.message,
            style_block(
                ("Bot", "PAN to Name DOB"),
                ("Type", "API Not Configured"),
                ("Action", "Owner must add an authorized PAN API"),
            ),
            reply_markup=main_keyboard(),
        )
        return

    if get_credits(uid) <= 0 and not is_lifetime(uid):
        await rsend(
            update.message,
            style_block(
                ("Bot", "Credits"),
                ("Type", "Insufficient Credits"),
                ("Action", "Refer friends"),
                ("Reward", "+1 Credit per referral"),
            ),
            reply_markup=main_keyboard(),
        )
        return

    prog = await rsend(
        update.message,
        style_block(
            ("System", "Searching"),
            ("Status", "Fetching PAN information"),
        ),
    )
    await run_loading_animation(prog, "Fetching PAN information")

    api_url = api_template.replace("{pan}", pan).replace("{PAN}", pan)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                api_url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"Accept": "application/json"},
            ) as resp:
                raw = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"HTTP {resp.status}")
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    raise RuntimeError("The API returned invalid JSON.")
    except Exception as e:
        await esend(
            prog,
            style_block(
                ("Bot", "API Error"),
                ("Type", "Request Failed"),
                ("Detail", str(e)[:80]),
            ),
        )
        return

    data = clean_api_data(data)
    data = sanitize_error_data(data)

    if is_empty_api_payload(data):
        await esend(
            prog,
            style_block(
                ("Bot", "PAN to Name DOB"),
                ("Type", "No Data Found"),
                ("Status", "No authorized result was returned"),
            ),
        )
        return

    deduct_credit(uid)
    remaining = get_credits(uid)
    if remaining <= 0:
        await check_and_auto_topup(ctx.bot, uid)
        remaining = get_credits(uid)

    json_text = html.escape(json.dumps(data, indent=2, ensure_ascii=False))
    result = (
        style_block(
            ("Bot", "PAN to Name DOB"),
            ("Type", "Result Found"),
            ("Credits", str(remaining)),
        )
        + f"\n\n<pre><code>{json_text}</code></pre>"
    )
    await esend(prog, result)


# ─── Mobile Info ──────────────────────────────────

async def start_mobile_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    credits = get_credits(uid)
    await rsend(
        update.message,
        style_block(
            ("Bot", "Mobile Info"),
            ("Type", "Premium Mobile Info"),
            ("Balance", f"{credits} Credits"),
            ("Charge", "1 Credit"),
            ("Input", "10 digit mobile"),
            ("Example", "9632580741"),
        ),
    )
    ctx.user_data["waiting_mobile"]  = True
    ctx.user_data["waiting_pan"]      = False
    ctx.user_data["waiting_number"]  = False
    ctx.user_data["waiting_tg"]      = False
    ctx.user_data["waiting_aadhar"]  = False
    ctx.user_data["waiting_vehicle"] = False


async def process_mobile(update: Update, ctx: ContextTypes.DEFAULT_TYPE, number: str):
    uid = update.effective_user.id
    number = number.strip()

    if not number.isdigit() or len(number) != 10:
        await rsend(
            update.message,
            style_block(
                ("Bot", "Mobile Info"),
                ("Type", "Invalid Number"),
                ("Need", "10 digit mobile"),
                ("Example", "9632580741"),
            ),
        )
        return

    ctx.user_data["waiting_mobile"] = False

    if get_credits(uid) <= 0 and not is_lifetime(uid):
        await rsend(
            update.message,
            style_block(
                ("Bot", "Credits"),
                ("Type", "Insufficient Credits"),
                ("Action", "Refer friends"),
                ("Reward", "+1 Credit per referral"),
            ),
            reply_markup=main_keyboard(),
        )
        return

    prog = await rsend(
        update.message,
        style_block(
            ("System", "Searching"),
            ("Status", "Searching database"),
        ),
    )

    await run_loading_animation(prog, "Searching database")

    api_template = get_setting("api_mobile")
    api_url = api_template.replace("{num}", number)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                data = await resp.json(content_type=None)
    except Exception as e:
        await esend(
            prog,
            style_block(
                ("Bot", "API Error"),
                ("Type", "Request Failed"),
                ("Detail", str(e)[:80]),
            ),
        )
        return

    data = clean_api_data(data)
    data = sanitize_error_data(data)
    deduct_credit(uid)
    remaining = get_credits(uid)
    if remaining <= 0:
        await check_and_auto_topup(ctx.bot, uid)
        remaining = get_credits(uid)
    json_text = html.escape(json.dumps(data, indent=2, ensure_ascii=False))

    result = (
        style_block(
            ("Bot", "Mobile Info"),
            ("Type", "Result Found"),
            ("Credits", str(remaining)),
        ) + f"\n\n<pre><code>{json_text}</code></pre>\n\n"
        + f'{P[2]} [⌯] {_to_bold("API BUY")} ⌁ <a href="http://t.me/UKRAINEBST">{_to_mono("UKRAINEBST")}</a>'
    )
    try:
        await esend(prog, result)
    except Exception:
        await rsend(update.message, result)


# ─── Refer & Balance ──────────────────────────────

async def show_refer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db_user = get_user(uid)
    if not db_user:
        return
    ref_code  = db_user[3]
    credits   = db_user[2]
    total_ref = get_refer_count(ref_code)
    bot_me    = await ctx.bot.get_me()
    ref_link  = f"https://t.me/{bot_me.username}?start=ref_{ref_code}"
    await rsend(
        update.message,
        style_block(
            ("Bot", "Refer And Earn"),
            ("Type", "Premium Referral"),
            ("Reward", "+1 Credit per friend"),
            ("Referred", f"{total_ref} users"),
            ("Credits", str(credits)),
            ("Link", "See below"),
        ) + f"\n\n<code>{ref_link}</code>",
    )


async def show_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db_user = get_user(uid)
    if not db_user:
        return
    ref_code  = db_user[3]
    credits   = db_user[2]
    total_ref = get_refer_count(ref_code)
    bal_val = "Lifetime" if is_lifetime(uid) else f"{credits:,}"
    await rsend(
        update.message,
        style_block(
            ("Bot", "Balance"),
            ("Type", "Account Status"),
            ("Credits", bal_val),
            ("Referrals", str(total_ref)),
            ("Cost", "1 Credit per search"),
        ),
    )


# ─── Ban / Unban ──────────────────────────────────

async def process_ban_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE, raw_id: str):
    ctx.user_data["waiting_ban_id"] = False
    raw_id = raw_id.strip()
    if not raw_id.lstrip("-").isdigit():
        await rsend(update.message, f"{P[11]} Invalid ID. Please send a numeric Telegram ID.")
        return

    target_id = int(raw_id)
    if is_staff(target_id):
        await rsend(update.message, f"{P[11]} You can't ban an owner/admin.")
        return

    ban_user(target_id)
    await rsend(
        update.message,
        style_block(
            ("Bot", "User Banned"),
            ("Type", "Ban Applied"),
            ("ID", str(target_id)),
            ("Credits", "0"),
        ),
    )
    try:
        ban_msg = await bsend(
            ctx.bot, target_id,
            style_block(
                ("Bot", "Banned"),
                ("Type", "Access Blocked"),
                ("Status", "Contact support"),
            ),
            reply_markup=appeal_keyboard(),
        )
        try:
            await ctx.bot.pin_chat_message(
                chat_id=target_id,
                message_id=ban_msg.message_id,
                disable_notification=True,
            )
        except Exception:
            pass
    except Exception:
        pass


async def cmd_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_staff(uid):
        await rsend(update.message, denied_block("No permission to use this bot.", uid))
        return
    args = ctx.args
    if not args or not args[0].lstrip("-").isdigit():
        await rsend(update.message, f"{P[14]} <b>Usage:</b> <code>/ban &lt;chat_id&gt;</code>")
        return
    await process_ban_id(update, ctx, args[0])


async def cmd_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_staff(uid):
        await rsend(update.message, denied_block("No permission to use this bot.", uid))
        return
    args = ctx.args
    if not args or not args[0].lstrip("-").isdigit():
        await rsend(update.message, f"{P[14]} <b>Usage:</b> <code>/unban &lt;chat_id&gt;</code>")
        return
    await process_unban_id(update, ctx, args[0])


async def process_unban_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE, raw_id: str):
    ctx.user_data["waiting_unban_id"] = False
    raw_id = raw_id.strip()
    if not raw_id.lstrip("-").isdigit():
        await rsend(update.message, f"{P[11]} Invalid ID. Please send a numeric Telegram ID.")
        return

    target_id = int(raw_id)
    ok = unban_user(target_id)

    if ok:
        await rsend(
            update.message,
            style_block(
                ("Bot", "User Unbanned"),
                ("Type", "Access Restored"),
                ("ID", str(target_id)),
                ("Credits", str(UNBAN_REFILL_CREDITS)),
            ),
        )
        try:
            await bsend(
                ctx.bot, target_id,
                style_block(
                    ("Bot", "Unbanned"),
                    ("Type", "Access Restored"),
                    ("Credits", str(UNBAN_REFILL_CREDITS)),
                    ("Status", "You can use the bot"),
                ),
                reply_markup=main_keyboard(),
            )
        except Exception:
            pass
    else:
        await rsend(
            update.message,
            style_block(
                ("Bot", "Unban"),
                ("Type", "Not Banned"),
                ("Status", "No action taken"),
            ),
        )


# ─── Add / Remove Admin ───────────────────────────

async def process_add_admin_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE, raw_id: str):
    ctx.user_data["waiting_add_admin_id"] = False
    raw_id = raw_id.strip()
    if not raw_id.lstrip("-").isdigit():
        await rsend(update.message, f"{P[11]} Invalid ID. Please send a numeric Telegram ID.")
        return

    target_id = int(raw_id)
    if is_owner(target_id):
        await rsend(update.message, f"{P[11]} That user is already the owner.")
        return

    added = add_dynamic_admin(target_id)
    if added:
        await rsend(
            update.message,
            f"{P[10]} <b>Admin Added!</b>\n\n"
            f"{P[48]} ID: <code>{target_id}</code>\n"
            f"{P[4]} This user now has admin privileges.",
        )
        try:
            await bsend(ctx.bot, target_id, f"{P[10]} Congratulations! You have been granted <b>Admin</b> access to this bot.")
        except Exception:
            pass
    else:
        await rsend(update.message, f"{P[25]} That user is already an admin or owner.")


async def process_remove_admin_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE, raw_id: str):
    ctx.user_data["waiting_remove_admin_id"] = False
    raw_id = raw_id.strip()
    if not raw_id.lstrip("-").isdigit():
        await rsend(update.message, f"{P[11]} Invalid ID. Please send a numeric Telegram ID.")
        return

    target_id = int(raw_id)
    if target_id in ADMIN_IDS:
        await rsend(update.message, f"{P[11]} Cannot remove static admins. Edit ADMIN_IDS in the code.")
        return

    removed = remove_dynamic_admin(target_id)
    if removed:
        await rsend(
            update.message,
            f"{P[47]} <b>Admin Removed!</b>\n\n"
            f"{P[48]} ID: <code>{target_id}</code>\n"
            f"{P[25]} Admin privileges revoked.",
        )
        try:
            await bsend(ctx.bot, target_id, f"{P[49]} Your admin access to this bot has been revoked.")
        except Exception:
            pass
    else:
        await rsend(update.message, f"{P[25]} That user was not a dynamic admin.")


async def process_minus_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE, raw_id: str):
    ctx.user_data["waiting_minus_id"] = False
    raw_id = raw_id.strip()
    if not raw_id.lstrip("-").isdigit():
        await rsend(update.message, f"{P[11]} Invalid ID. Please send a numeric Telegram ID.")
        return
    target_id = int(raw_id)
    if not get_user(target_id):
        await rsend(update.message, f"{P[11]} User not found in database.")
        return
    ctx.user_data["minus_target_id"] = target_id
    ctx.user_data["waiting_minus_amount"] = True
    bal = get_credits(target_id)
    life = " (Lifetime)" if is_lifetime(target_id) else ""
    await rsend(
        update.message,
        f"{P[11]} <b>Minus Credits</b>\n\n"
        f"{P[48]} User: <code>{target_id}</code>{life}\n"
        f"{P[2]} Current Balance: <b>{bal:,}</b>\n\n"
        f"{P[22]} How many credits should be removed? Send a positive number.\n"
        f"{P[26]} Send /cancel to abort.",
    )


async def process_minus_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE, raw_amount: str):
    ctx.user_data["waiting_minus_amount"] = False
    raw_amount = raw_amount.strip()
    if not raw_amount.isdigit() or int(raw_amount) <= 0:
        ctx.user_data["waiting_minus_amount"] = True
        await rsend(update.message, f"{P[11]} Invalid amount. Please send a positive whole number.")
        return
    amount = int(raw_amount)
    target_id = ctx.user_data.pop("minus_target_id", None)
    if not target_id:
        await rsend(update.message, f"{P[11]} Something went wrong. Use /panel again.")
        return
    ok, new_bal = deduct_credits_amount(target_id, amount)
    if not ok:
        await rsend(update.message, f"{P[11]} User not found.")
        return
    await rsend(
        update.message,
        f"{P[47]} <b>Credits Deducted!</b>\n\n"
        f"{P[48]} User: <code>{target_id}</code>\n"
        f"{P[11]} Removed: <b>-{amount:,}</b>\n"
        f"{P[3]} New Balance: <b>{new_bal:,}</b>",
        reply_markup=admin_panel_keyboard(update.effective_user.id),
    )
    try:
        await bsend(
            ctx.bot, target_id,
            f"{P[11]} <b>Credits Updated</b>\n\n"
            f"{P[25]} An admin removed <b>{amount:,}</b> credits from your balance.\n"
            f"{P[3]} New Balance: <b>{new_bal:,}</b>",
        )
    except Exception:
        pass



# ═══════════════════════════════════════════════════
#                 ADMIN COMMANDS
# ═══════════════════════════════════════════════════


async def cmd_setids(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return
    uid = update.effective_user.id
    if not is_owner(uid):
        await rsend(update.message, denied_block("Owner only.", uid))
        return

    args = ctx.args or []
    main_id = get_setting("main_channel_id") or get_setting("private_channel_id") or "— not set —"
    backup_id = get_setting("backup_channel_id") or "— not set —"
    group_id = get_setting("group_id") or "— not set —"

    if not args:
        await rsend(
            update.message,
            style_block(
                ("Bot", "Chat IDs"),
                ("Main", str(main_id)),
                ("Backup", str(backup_id)),
                ("Group", str(group_id)),
                ("Usage", "/setids main -100xxxx"),
            ) + "\n\n"
            + f"{P[25]} Forward a chat message to <code>@userinfobot</code> to get the numeric ID.\n"
            + f"{P[11]} Then: <code>/setids main -1001234567890</code>",
        )
        return

    if len(args) < 2:
        await rsend(
            update.message,
            style_block(
                ("Bot", "Set IDs"),
                ("Usage", "/setids main|backup|group <id>"),
                ("Example", "/setids main -1001234567890"),
            ),
        )
        return

    kind = args[0].strip().lower()
    raw_id = args[1].strip()
    if not raw_id.lstrip("-").isdigit():
        await rsend(
            update.message,
            style_block(
                ("Bot", "Set IDs"),
                ("Error", "ID must be numeric"),
                ("Example", "-1001234567890"),
            ),
        )
        return

    key_map = {
        "main": ("main_channel_id", "Main Channel"),
        "private": ("main_channel_id", "Main Channel"),
        "backup": ("backup_channel_id", "Backup Channel"),
        "group": ("group_id", "Group"),
    }
    if kind not in key_map:
        await rsend(
            update.message,
            style_block(
                ("Bot", "Set IDs"),
                ("Error", "Unknown type"),
                ("Use", "main | backup | group"),
            ),
        )
        return

    key, label = key_map[kind]
    set_setting(key, raw_id)
    if kind in ("main", "private"):
        set_setting("private_channel_id", raw_id)

    await rsend(
        update.message,
        style_block(
            ("Bot", "Chat ID Saved"),
            ("Type", label),
            ("ID", raw_id),
            ("Status", "Membership checks active"),
        ),
    )


async def cmd_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return
    uid = update.effective_user.id
    if not is_staff(uid):
        await rsend(update.message, denied_block("No permission to use this bot.", uid))
        return

    role = "OWNER" if is_owner(uid) else "ADMIN"
    await rsend(
        update.message,
        style_block(
            ("Bot", f"{role} PANEL"),
            ("Type", "Admin Control"),
            ("Status", "Active"),
        ),
        reply_markup=admin_panel_keyboard(uid),
    )


async def cb_credit_review(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id

    if not is_staff(uid):
        await query.answer("Not authorized.", show_alert=True)
        return

    data = query.data or ""
    if data.startswith("credit_ban|"):
        try:
            target_id = int(data.split("|", 1)[1])
        except ValueError:
            await query.answer("Invalid ID.", show_alert=True)
            return

        if is_staff(target_id):
            await query.answer("Cannot ban owner/admin!", show_alert=True)
            return

        ban_user(target_id, reason="admin_credit_review")
        await query.answer("User banned. Credits set to 0.", show_alert=True)
        try:
            await esend(
                query.message,
                ban_admin_notice_5000(target_id) + f"\n\n{P[4]} Action by: <code>{uid}</code>",
            )
        except Exception:
            pass
        try:
            ban_msg = await bsend(
                ctx.bot, target_id,
                ban_notice_5000_text(),
                reply_markup=appeal_keyboard(),
            )
            try:
                await ctx.bot.pin_chat_message(
                    chat_id=target_id,
                    message_id=ban_msg.message_id,
                    disable_notification=True,
                )
            except Exception:
                pass
        except Exception:
            pass
        return

    if data.startswith("credit_reject|"):
        try:
            target_id = int(data.split("|", 1)[1])
        except ValueError:
            await query.answer("Invalid ID.", show_alert=True)
            return

        await query.answer("Rejected — user kept as is.", show_alert=True)
        try:
            await esend(
                query.message,
                f"{P[3]} <b>Rejected</b>\n\n"
                f"{P[48]} User: <code>{target_id}</code>\n"
                f"{P[5]} No ban applied. Credits unchanged.\n"
                f"{P[4]} Action by: <code>{uid}</code>",
            )
        except Exception:
            pass
        return


async def cb_admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if not is_staff(uid):
        await query.answer("Not authorized.", show_alert=True)
        return

    data = query.data

    if data == "back_admin":
        await esend(
            query.message,
            f"{P[10]} <b>{'OWNER' if is_owner(uid) else 'ADMIN'} PANEL</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{P[6]} Manage the bot from here.\n"
            "━━━━━━━━━━━━━━━━━━━━",
            reply_markup=admin_panel_keyboard(uid),
        )
        return

    
    if data == "admin_download_db":
        if not is_owner(uid):
            await query.answer("Only owners can download DB.", show_alert=True)
            return
        await query.answer("Sending bot.db…", show_alert=False)
        try:
            if not os.path.exists(DB_PATH):
                await esend(query.message, style_line("Error", "bot.db not found"))
                return
            with open(DB_PATH, "rb") as f:
                await ctx.bot.send_document(
                    chat_id=uid,
                    document=f,
                    filename="bot.db",
                    caption=style_line("Database", "bot.db") + "\n" + style_line("Status", "Download ready"),
                )
            await esend(
                query.message,
                style_line("Database", "Sent") + "\n" + style_line("File", "bot.db"),
                reply_markup=admin_panel_keyboard(uid),
            )
        except Exception as e:
            await esend(
                query.message,
                style_line("Error", str(e)[:80]),
                reply_markup=admin_panel_keyboard(uid),
            )
        return

    if data == "toggle_bot_status":
        new_val = toggle_button("bot_on")
        label = "ON" if new_val == "1" else "OFF"
        await query.answer(f"Bot status is now {label}", show_alert=False)
        await esend(
            query.message,
            f"{P[10]} <b>{'OWNER' if is_owner(uid) else 'ADMIN'} PANEL</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{P[6]} Manage the bot from here.\n"
            "━━━━━━━━━━━━━━━━━━━━",
            reply_markup=admin_panel_keyboard(uid),
        )
        return

    if data == "toggle_group_status":
        new_val = toggle_button("group_status")
        label = "ON" if new_val == "1" else "OFF"
        await query.answer(f"Group Status is now {label}", show_alert=False)
        await esend(
            query.message,
            f"{P[10]} <b>{'OWNER' if is_owner(uid) else 'ADMIN'} PANEL</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{P[6]} Manage the bot from here.\n"
            "━━━━━━━━━━━━━━━━━━━━",
            reply_markup=admin_panel_keyboard(uid),
        )
        return

    if data == "admin_remove_broadcast":
        rows_bc = list_broadcasts(15)
        if not rows_bc:
            await query.answer("No broadcasts logged yet.", show_alert=True)
            return
        kb_rows = []
        for bid, admin_id, preview, created in rows_bc:
            label = f"#{bid} · {str(created)[:16]} · {(preview or '')[:24]}"
            kb_rows.append([IKB(label, callback_data=f"bc_del|{bid}", style="danger")])
        kb_rows.append([IKB("Back", callback_data="back_admin", style="primary", icon_custom_emoji_id="5445365692004071819")])
        await esend(
            query.message,
            f"{P[11]} <b>Remove Old Broadcast</b>\n\n"
            f"{P[25]} Tap a broadcast to delete it from user DMs.",
            reply_markup=InlineKeyboardMarkup(kb_rows),
        )
        return

    if data and data.startswith("bc_del|"):
        try:
            bid = int(data.split("|", 1)[1])
        except ValueError:
            await query.answer("Invalid id.", show_alert=True)
            return
        deliveries = get_broadcast_deliveries(bid)
        if not deliveries:
            delete_broadcast_log(bid)
            await query.answer("No stored messages for this broadcast.", show_alert=True)
            await esend(
                query.message,
                f"{P[11]} <b>No Messages Found</b>\n\n"
                f"{P[4]} ID: <code>{bid}</code>\n"
                f"{P[25]} Nothing to delete (no delivery log).",
                reply_markup=admin_panel_keyboard(uid),
            )
            return

        await query.answer("Deleting live…", show_alert=False)
        deleted = 0
        failed = 0
        try:
            await esend(
                query.message,
                f"{P[19]} <b>Deleting broadcast messages…</b>\n\n"
                f"{P[4]} ID: <code>{bid}</code>\n"
                f"{P[3]} Total targets: <b>{len(deliveries)}</b>\n"
                f"{P[25]} Please wait — messages are being removed live.",
            )
        except Exception:
            pass

        for i, (user_id, message_id) in enumerate(deliveries):
            try:
                try:
                    await ctx.bot.unpin_chat_message(chat_id=user_id, message_id=message_id)
                except Exception:
                    pass
                await ctx.bot.delete_message(chat_id=user_id, message_id=message_id)
                deleted += 1
            except Exception:
                failed += 1
            if (i + 1) % 25 == 0:
                try:
                    await esend(
                        query.message,
                        f"{P[19]} <b>Deleting broadcast messages…</b>\n\n"
                        f"{P[4]} ID: <code>{bid}</code>\n"
                        f"{P[3]} Deleted: <b>{deleted}</b> | Failed: <b>{failed}</b>\n"
                        f"{P[25]} Progress: <b>{i + 1}</b>/<b>{len(deliveries)}</b>",
                    )
                except Exception:
                    pass
            await asyncio.sleep(0.05)

        delete_broadcast_log(bid)
        await esend(
            query.message,
            f"{P[9]} <b>Broadcast Removed (Live)</b>\n\n"
            f"{P[4]} ID: <code>{bid}</code>\n"
            f"{P[3]} Deleted: <b>{deleted}</b>\n"
            f"{P[11]} Failed: <b>{failed}</b>\n"
            f"{P[2]} Total processed: <b>{len(deliveries)}</b>",
            reply_markup=admin_panel_keyboard(uid),
        )
        return

    if data == "admin_all_credit":
        ctx.user_data["waiting_all_credit_count"] = True
        ctx.user_data["waiting_all_credit_amount"] = False
        ctx.user_data["all_credit_member_count"] = None
        await esend(
            query.message,
            f"{ALL_CREDIT_EMOJI} <b>All Credit</b>\n\n"
            f"{P[22]} How many members should receive credits?\n"
            f"{P[26]} Send a positive whole number.\n\n"
            f"{P[11]} Send /cancel to abort.",
        )
        return

    if data == "admin_minus_credit":
        ctx.user_data["waiting_minus_id"] = True
        ctx.user_data["waiting_minus_amount"] = False
        ctx.user_data["minus_target_id"] = None
        await esend(
            query.message,
            f"{P[11]} <b>Minus Credits</b>\n\n"
            f"{P[25]} Send the Telegram <b>ID</b> of the user.\n"
            f"{P[26]} Send /cancel to abort.",
        )
        return

    if data == "admin_ban_user":
        ctx.user_data["waiting_ban_id"]   = True
        ctx.user_data["waiting_unban_id"] = False
        await esend(
            query.message,
            f"{P[11]} <b>Ban User</b>\n\n"
            f"{P[25]} Send the Telegram <b>ID</b> of the user you want to ban.\n"
            f"{P[26]} Send /cancel to abort.",
        )
        return

    if data == "admin_unban_user":
        ctx.user_data["waiting_unban_id"] = True
        ctx.user_data["waiting_ban_id"]   = False
        await esend(
            query.message,
            f"{P[3]} <b>Unban User</b>\n\n"
            f"{P[25]} Send the Telegram <b>ID</b> of the user you want to unban.\n"
            f"{P[26]} On unban, user gets <b>{UNBAN_REFILL_CREDITS:,}</b> credits.\n"
            f"{P[26]} Send /cancel to abort.",
        )
        return

    if data == "admin_add_admin":
        if not is_owner(uid):
            await query.answer("Only the owner can add admins.", show_alert=True)
            return
        ctx.user_data["waiting_add_admin_id"]    = True
        ctx.user_data["waiting_remove_admin_id"] = False

        dyn_admins = get_dynamic_admins()
        admin_list = "\n".join([f"  • <code>{a}</code>" for a in dyn_admins]) if dyn_admins else "  <i>None yet</i>"
        await esend(
            query.message,
            f"{P[10]} <b>Add Admin</b>\n\n"
            f"{P[25]} Send the Telegram <b>ID</b> of the user to make admin.\n\n"
            f"{P[4]} <b>Current Dynamic Admins:</b>\n{admin_list}\n\n"
            f"{P[26]} Send /cancel to abort.",
        )
        return

    if data == "admin_remove_admin":
        if not is_owner(uid):
            await query.answer("Only the owner can remove admins.", show_alert=True)
            return
        ctx.user_data["waiting_remove_admin_id"] = True
        ctx.user_data["waiting_add_admin_id"]    = False

        dyn_admins = get_dynamic_admins()
        admin_list = "\n".join([f"  • <code>{a}</code>" for a in dyn_admins]) if dyn_admins else "  <i>None yet</i>"
        await esend(
            query.message,
            f"{P[47]} <b>Remove Admin</b>\n\n"
            f"{P[25]} Send the Telegram <b>ID</b> of the admin to remove.\n\n"
            f"{P[4]} <b>Current Dynamic Admins:</b>\n{admin_list}\n\n"
            f"{P[26]} Send /cancel to abort.",
        )
        return

    if data == "admin_buttons":
        await esend(
            query.message,
            f"{P[17]} <b>Button Management</b>\n\n"
            "Tap a button to toggle it ON or OFF.\n"
            "ON = green, OFF = red. Premium icons enabled.\n"
            "Changes take effect immediately.",
            reply_markup=buttons_manage_keyboard(),
        )
        return

    toggle_map = {
        "toggle_btn_num":    "btn_num",
        "toggle_btn_tg":     "btn_tg",
        "toggle_btn_aadhar": "btn_aadhar",
        "toggle_btn_vehicle":"btn_vehicle",
        "toggle_btn_pan":    "btn_pan",
        "toggle_btn_refer":  "btn_refer",
        "toggle_btn_balance":"btn_balance",
        "toggle_btn_mobile": "btn_mobile",
    }
    if data in toggle_map:
        new_state = toggle_button(toggle_map[data])
        label = "ON" if new_state == "1" else "OFF"
        btn_name = {
            "toggle_btn_num":    "Number to Info",
            "toggle_btn_tg":     "TG to Number",
            "toggle_btn_aadhar": "Aadhar to Info",
            "toggle_btn_vehicle":"Vehicle to Info",
            "toggle_btn_pan":    "PAN to Name DOB",
            "toggle_btn_refer":  "Refer",
            "toggle_btn_balance":"Balance",
            "toggle_btn_mobile": "Mobile Info",
        }[data]
        await query.answer(f"{btn_name} is now {label}", show_alert=False)
        await esend(
            query.message,
            f"{P[17]} <b>Button Management</b>\n\n"
            "Tap a button to toggle it ON or OFF.\n"
            "ON = green, OFF = red. Premium icons enabled.\n"
            "Changes take effect immediately.",
            reply_markup=buttons_manage_keyboard(),
        )
        return

    if data == "admin_filter_keys":
        keys = get_filter_keys()
        keys_text = "\n".join([f"  • <code>{html.escape(k)}</code>" for k in keys]) if keys else "  <i>None yet</i>"
        await esend(
            query.message,
            f"{P[14]} <b>Manage Filter Keys</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{P[6]} These keys are <b>deleted</b> from all API responses before showing them to users.\n\n"
            f"{P[4]} <b>Current Filter Keys:</b>\n{keys_text}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{P[5]} Tap 🗑 next to a key to remove it, or Add New Key to add one.",
            reply_markup=filter_keys_keyboard(),
        )
        return

    if data == "fk_add":
        ctx.user_data["waiting_fk_add"] = True
        text = (
            f"{P[4]} <b>Add Filter Key</b>\n\n"
            f"{P[25]} Send the <b>JSON key name</b> you want to strip from API responses.\n"
            f"{P[27]} Example: <code>credit</code> or <code>developer</code>\n\n"
            f"{P[26]} Send /cancel to abort."
        )
        try:
            await esend(query.message, text)
        except Exception:
            await bsend(ctx.bot, uid, text)
        return

    if data and data.startswith("fk_del|"):
        key_to_del = data.split("|", 1)[1]
        removed = remove_filter_key(key_to_del)
        msg = f"✅ Key {key_to_del} removed." if removed else "⚠️ Key not found."
        await query.answer(msg, show_alert=False)
        keys = get_filter_keys()
        keys_text = "\n".join([f"  • <code>{html.escape(k)}</code>" for k in keys]) if keys else "  <i>None yet</i>"
        await esend(
            query.message,
            f"{P[14]} <b>Manage Filter Keys</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{P[6]} These keys are <b>deleted</b> from all API responses before showing them to users.\n\n"
            f"{P[4]} <b>Current Filter Keys:</b>\n{keys_text}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{P[5]} Tap 🗑 next to a key to remove it, or Add New Key to add one.",
            reply_markup=filter_keys_keyboard(),
        )
        return

    if data == "admin_apis":
        if not is_owner(uid):
            await query.answer("Only the owner can manage APIs.", show_alert=True)
            return
        num_api     = get_setting("api_num")
        tg_api      = get_setting("api_tg")
        aadhar_api  = get_setting("api_aadhar")
        vehicle_api = get_setting("api_vehicle")
        pan_api     = get_setting("api_pan")
        mobile_api  = get_setting("api_mobile")
        await esend(
            query.message,
            f"{P[18]} <b>API Management</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Number Info:</b> {'✅ Configured' if num_api else '— not set —'}\n\n"
            f"<b>TG to Number:</b> {'✅ Configured' if tg_api else '— not set —'}\n\n"
            f"<b>Aadhar Info:</b> {'✅ Configured' if aadhar_api else '— not set —'}\n\n"
            f"<b>Vehicle to Info:</b> {'✅ Configured' if vehicle_api else '— not set —'}\n\n"
            f"<b>PAN to Name DOB:</b> {'✅ Configured' if pan_api else '— not configured —'}\n\n"
            f"<b>Mobile Info:</b> {'✅ Configured' if mobile_api else '— not set —'}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{P[5]} Tap ✏️ to change a URL, or 🗑 Delete to clear it.\n"
            f"{P[26]} Use <code>{{num}}</code>, <code>{{chatid}}</code>, <code>{{id}}</code>, <code>{{vehicle}}</code> as placeholders.",
            reply_markup=apis_manage_keyboard(),
        )
        return

    delete_api_map = {
        "delete_api_num":     ("api_num",     "Number Info"),
        "delete_api_tg":      ("api_tg",      "TG to Number"),
        "delete_api_aadhar":  ("api_aadhar",  "Aadhar Info"),
        "delete_api_vehicle": ("api_vehicle", "Vehicle to Info"),
        "delete_api_pan":     ("api_pan",     "PAN to Name DOB"),
        "delete_api_mobile":  ("api_mobile",  "Mobile Info"),
    }
    if data in delete_api_map:
        if not is_owner(uid):
            await query.answer("Only the owner can manage APIs.", show_alert=True)
            return
        key, label = delete_api_map[data]
        set_setting(key, "")
        await query.answer(f"{label} API deleted.", show_alert=False)
        num_api     = get_setting("api_num")
        tg_api      = get_setting("api_tg")
        aadhar_api  = get_setting("api_aadhar")
        vehicle_api = get_setting("api_vehicle")
        pan_api     = get_setting("api_pan")
        mobile_api  = get_setting("api_mobile")
        await esend(
            query.message,
            f"{P[18]} <b>API Management</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Number Info:</b> {'✅ Configured' if num_api else '— not set —'}\n\n"
            f"<b>TG to Number:</b> {'✅ Configured' if tg_api else '— not set —'}\n\n"
            f"<b>Aadhar Info:</b> {'✅ Configured' if aadhar_api else '— not set —'}\n\n"
            f"<b>Vehicle to Info:</b> {'✅ Configured' if vehicle_api else '— not set —'}\n\n"
            f"<b>PAN to Name DOB:</b> {'✅ Configured' if pan_api else '— not configured —'}\n\n"
            f"<b>Mobile Info:</b> {'✅ Configured' if mobile_api else '— not set —'}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{P[5]} Tap ✏️ to change a URL, or 🗑 Delete to clear it.\n"
            f"{P[26]} Use <code>{{num}}</code>, <code>{{chatid}}</code>, <code>{{id}}</code>, <code>{{vehicle}}</code> as placeholders.",
            reply_markup=apis_manage_keyboard(),
        )
        return

    api_edit_map = {
        "edit_api_num":     ("api_num",     "Number Info",    "{num}"),
        "edit_api_tg":      ("api_tg",      "TG to Number",   "{chatid}"),
        "edit_api_aadhar":  ("api_aadhar",  "Aadhar Info",    "{id}"),
        "edit_api_vehicle": ("api_vehicle", "Vehicle to Info","{vehicle}"),
        "edit_api_pan":     ("api_pan",     "PAN to Name DOB","{pan}"),
        "edit_api_mobile":  ("api_mobile",  "Mobile Info",    "{num}"),
    }
    if data in api_edit_map:
        if not is_owner(uid):
            await query.answer("Only the owner can manage APIs.", show_alert=True)
            return
        key, label, placeholder = api_edit_map[data]
        ctx.user_data["editing_api_key"]   = key
        ctx.user_data["editing_api_label"] = label
        current = get_setting(key)
        await esend(
            query.message,
            f"{P[14]} <b>Edit {label} API</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{P[22]} <b>Current URL:</b> {'Configured (hidden for security)' if current else 'Not configured'}\n\n"
            f"{P[23]} Send the new API URL. It will be stored privately and not displayed back.\n"
            f"{P[27]} Use <code>{html.escape(placeholder)}</code> as the input placeholder.\n\n"
            f"{P[11]} Send /cancel to cancel.",
        )
        ctx.user_data["waiting_api_edit"] = True
        return


async def receive_filter_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return
    uid = update.effective_user.id
    if not is_staff(uid):
        return

    new_key = update.message.text.strip()
    ctx.user_data["waiting_fk_add"] = False

    if not new_key:
        await rsend(update.message, f"{P[11]} Key cannot be empty. Use /panel to try again.")
        return

    keys_before = get_filter_keys()
    if len(keys_before) >= MAX_FILTER_KEYS:
        await rsend(
            update.message,
            f"{P[11]} <b>Filter key limit reached</b>\n\n"
            f"{P[25]} Maximum <b>{MAX_FILTER_KEYS}</b> filter keys allowed.\n"
            f"{P[5]} Remove an existing key before adding a new one.",
            reply_markup=filter_keys_keyboard(),
        )
        return

    added = add_filter_key(new_key)
    if added:
        keys = get_filter_keys()
        keys_text = "\n".join([f"  • <code>{html.escape(k)}</code>" for k in keys]) if keys else "  <i>None yet</i>"
        await rsend(
            update.message,
            f"{P[9]} <b>Filter Key Added!</b>\n\n"
            f"Key <code>{html.escape(new_key)}</code> added successfully.\n\n"
            f"{P[4]} <b>Active Filter Keys ({len(keys)}/{MAX_FILTER_KEYS}):</b>\n{keys_text}\n\n"
            f"{P[5]} Tap Add New Key to add more keys.",
            reply_markup=filter_keys_keyboard(),
        )
    else:
        keys = get_filter_keys()
        keys_text = "\n".join([f"  • <code>{html.escape(k)}</code>" for k in keys]) if keys else "  <i>None yet</i>"
        await rsend(
            update.message,
            f"{P[5]} Key <code>{html.escape(new_key)}</code> already exists.\n\n"
            f"{P[4]} <b>Active Filter Keys ({len(keys)}/{MAX_FILTER_KEYS}):</b>\n{keys_text}",
            reply_markup=filter_keys_keyboard(),
        )


async def receive_api_value(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return
    uid = update.effective_user.id
    if not is_owner(uid):
        return

    new_url = update.message.text.strip()
    key   = ctx.user_data.get("editing_api_key")
    label = ctx.user_data.get("editing_api_label", "API")

    if not key:
        await rsend(update.message, f"{P[11]} Something went wrong. Use /panel to try again.")
        return

    set_setting(key, new_url)
    ctx.user_data["waiting_api_edit"] = False
    ctx.user_data["editing_api_key"]  = None

    await rsend(
        update.message,
        f"{P[9]} <b>{label} API Updated!</b>\n\n"
        f"{P[2]} API URL securely saved. The secret URL is hidden from the bot interface.",
        reply_markup=admin_panel_keyboard(uid),
    )


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return
    uid = update.effective_user.id
    if not is_owner(uid):
        await rsend(update.message, denied_block("No permission to use this bot.", uid))
        return
    s = get_stats()
    await rsend(
        update.message,
        f"{P[10]} <b>BOT STATISTICS</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{P[0]} <b>Users</b>\n"
        f"{P[22]}  Total Users     : <b>{s['total_users']}</b>\n"
        f"{P[23]}  Verified Users  : <b>{s['verified_users']}</b>\n"
        f"{P[27]}  Unverified      : <b>{s['total_users'] - s['verified_users']}</b>\n\n"
        f"{P[2]} <b>Credits</b>\n"
        f"{P[22]}  Total in Bot    : <b>{s['total_credits']:,}</b>\n\n"
        f"{P[7]} <b>Referrals</b>\n"
        f"{P[22]}  Total Referrals : <b>{s['total_referrals']}</b>\n\n"
        f"{P[6]} <b>Redeem Codes</b>\n"
        f"{P[22]}  Codes Created   : <b>{s['total_codes']}</b>\n"
        f"{P[23]}  Total Redeemed  : <b>{s['total_redeems']}</b>\n\n"
        f"{P[10]} <b>Admins</b>\n"
        f"{P[22]}  Dynamic Admins  : <b>{s['dynamic_admins']}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━",
    )


async def cmd_create(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_owner(uid):
        await rsend(update.message, denied_block("No permission to use this bot.", uid))
        return
    args = ctx.args
    if len(args) != 2 or not args[0].isdigit() or not args[1].isdigit():
        await rsend(update.message, f"{P[17]} <b>Usage:</b> <code>/create &lt;credits&gt; &lt;max_users&gt;</code>")
        return
    credits  = int(args[0])
    max_uses = int(args[1])
    code     = create_redeem_code(credits, max_uses)
    await rsend(
        update.message,
        f"{P[10]} <b>REDEEM CODE CREATED</b>\n\n"
        f"{P[2]} Code        : <code>{code}</code>\n"
        f"{P[4]} Total Uses  : {max_uses}\n"
        f"{P[3]} Per Redeem  : {credits:,} Credits\n"
        f"{P[9]} Total Value : {credits * max_uses:,} Credits",
    )


async def cmd_addcredits(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_staff(uid):
        await rsend(update.message, denied_block("No permission to use this bot.", uid))
        return
    args = ctx.args
    if len(args) != 2 or not args[0].lstrip("-").isdigit() or not args[1].isdigit():
        await rsend(
            update.message,
            f"{P[14]} <b>Usage:</b> <code>/addcredits &lt;user_id&gt; &lt;amount&gt;</code>",
        )
        return
    target_id = int(args[0])
    amount    = int(args[1])
    if amount <= 0:
        await update.message.reply_text("Amount must be greater than 0.")
        return
    ok, result = try_admin_add_credits(target_id, amount)
    if not ok:
        if result == "not_found":
            await update.message.reply_text(f"User {target_id} not found.")
        else:
            await update.message.reply_text("Failed.")
        return
    new_bal = result
    await rsend(
        update.message,
        f"{P[21]} <b>Credits Added!</b>\n\n"
        f"{P[4]} User ID    : <code>{target_id}</code>\n"
        f"{P[2]} Added      : <b>+{amount:,}</b>\n"
        f"{P[3]} New Balance: <b>{new_bal:,}</b>",
    )
    try:
        await bsend(
            ctx.bot, target_id,
            f"{P[8]} <b>Credits Added!</b>\n\n"
            f"{P[2]} <b>+{amount:,} Credits</b> added!\n"
            f"{P[9]} New Balance: <b>{new_bal:,}</b>",
        )
    except Exception:
        pass
    if not is_staff(target_id):
        await notify_staff_credit_add(
            ctx.bot, target_id, amount, new_bal,
            source="Admin",
            extra=f"/addcredits by {uid}",
        )


async def cmd_le(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_staff(uid):
        await rsend(update.message, denied_block("No permission to use this bot.", uid))
        return

    reply = update.message.reply_to_message
    if reply is None or reply.from_user is None:
        await rsend(
            update.message,
            f"{P[14]} <b>Reply Required</b>\n\n"
            f"{P[22]} Reply to a member's message and use <code>/le 5000</code>.",
        )
        return

    args = ctx.args
    if len(args) != 1 or not args[0].isdigit() or int(args[0]) <= 0:
        await rsend(
            update.message,
            f"{P[14]} <b>Usage:</b> Reply to a member's message with "
            f"<code>/le &lt;credits&gt;</code>\n\n"
            f"{P[22]} Example: <code>/le 5000</code>",
        )
        return

    target_id = reply.from_user.id
    amount = int(args[0])
    ok, result = try_admin_add_credits(target_id, amount)
    if not ok:
        if result == "not_found":
            await rsend(
                update.message,
                f"{P[11]} <b>User Not Found</b>\n\n"
                f"{P[25]} That member must start and verify the bot before credits can be added.",
            )
        return

    new_balance = result
    await rsend(
        update.message,
        f"{LE_CREDIT_EMOJI} <b>Credits Added!</b>\n\n"
        f"{P[4]} Member: <code>{target_id}</code>\n"
        f"{P[2]} Added: <b>+{amount:,}</b>\n"
        f"{P[3]} New Balance: <b>{new_balance:,}</b>",
    )
    try:
        await bsend(
            ctx.bot,
            target_id,
            f"{LE_CREDIT_EMOJI} <b>Credits Added!</b>\n\n"
            f"{P[2]} <b>+{amount:,} Credits</b> were added to your balance.\n"
            f"{P[3]} New Balance: <b>{new_balance:,}</b>",
        )
    except Exception:
        pass
    if not is_staff(target_id):
        await notify_staff_credit_add(
            ctx.bot, target_id, amount, new_balance,
            source="Admin",
            extra=f"/le by {uid}",
        )


async def process_all_credit_count(update: Update, ctx: ContextTypes.DEFAULT_TYPE, raw_count: str):
    ctx.user_data["waiting_all_credit_count"] = False

    if not raw_count.isdigit() or int(raw_count) <= 0:
        ctx.user_data["waiting_all_credit_count"] = True
        await rsend(
            update.message,
            f"{P[11]} <b>Invalid member count.</b>\n\n"
            f"{P[5]} Please send a positive whole number, such as <code>100</code>.",
        )
        return

    member_count = int(raw_count)
    available_members = len(get_all_user_ids())
    if available_members == 0:
        await rsend(
            update.message,
            f"{P[11]} <b>No members found.</b>\n\n"
            f"{P[25]} There are no registered members to credit.",
            reply_markup=admin_panel_keyboard(update.effective_user.id),
        )
        return

    actual_count = min(member_count, available_members)
    ctx.user_data["all_credit_member_count"] = actual_count
    ctx.user_data["waiting_all_credit_amount"] = True
    await rsend(
        update.message,
        f"{ALL_CREDIT_EMOJI} <b>All Credit</b>\n\n"
        f"{P[4]} Members selected: <b>{actual_count:,}</b>\n\n"
        f"{P[22]} How many credits should be added to each member?\n"
        f"{P[26]} Send a positive whole number.\n\n"
        f"{P[11]} Send /cancel to abort.",
    )


async def process_all_credit_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE, raw_amount: str):
    ctx.user_data["waiting_all_credit_amount"] = False

    if not raw_amount.isdigit() or int(raw_amount) <= 0:
        ctx.user_data["waiting_all_credit_amount"] = True
        await rsend(
            update.message,
            f"{P[11]} <b>Invalid credit amount.</b>\n\n"
            f"{P[5]} Please send a positive whole number, such as <code>50</code>.",
        )
        return

    amount = int(raw_amount)
    member_count = int(ctx.user_data.pop("all_credit_member_count", 0) or 0)
    target_ids = get_user_ids_for_credit(member_count)
    if not target_ids:
        await rsend(
            update.message,
            f"{P[11]} <b>No members found.</b>\n\n"
            f"{P[25]} No balances were changed.",
            reply_markup=admin_panel_keyboard(update.effective_user.id),
        )
        return

    credited = 0
    total_added = 0
    for target_id in target_ids:
        ok, result = try_admin_add_credits(target_id, amount)
        if ok:
            credited += 1
            total_added += amount
            new_bal = result
            try:
                await bsend(
                    ctx.bot, target_id,
                    f"{ALL_CREDIT_EMOJI} <b>Credits Received!</b>\n\n"
                    f"{P[2]} <b>+{amount:,} Credits</b> added by admin (All Credit).\n"
                    f"{P[3]} New Balance: <b>{new_bal:,}</b>",
                )
            except Exception:
                pass

    await rsend(
        update.message,
        f"{ALL_CREDIT_EMOJI} <b>All Credit Complete!</b>\n\n"
        f"{P[4]} Members credited: <b>{credited:,}</b>\n"
        f"{P[2]} Credits added to each: <b>+{amount:,}</b>\n"
        f"{P[3]} Total credits added: <b>{total_added:,}</b>\n"
        f"{P[5]} Each user was notified.",
        reply_markup=admin_panel_keyboard(update.effective_user.id),
    )


async def _apply_redeem(update: Update, ctx: ContextTypes.DEFAULT_TYPE, code: str):
    uid = update.effective_user.id
    code = code.strip().upper()
    ok, value = use_redeem_code(code, uid)
    if not ok:
        msgs = {
            "invalid": style_block(("Bot", "Redeem"), ("Type", "Invalid Code"), ("Status", "Does not exist")),
            "expired": style_block(("Bot", "Redeem"), ("Type", "Code Expired"), ("Status", "Fully redeemed")),
            "already_used": style_block(("Bot", "Redeem"), ("Type", "Already Used"), ("Status", "Already redeemed")),
        }
        await rsend(update.message, msgs.get(value, style_block(("Bot", "Redeem"), ("Type", "Error"))))
        return False

    new_credits = get_credits(uid)
    await rsend(
        update.message,
        style_block(
            ("Bot", "Redeem"),
            ("Type", "Claim Success"),
            ("Reward", f"+{value} Credits"),
            ("Balance", f"{new_credits} Credits"),
        ),
        reply_markup=main_keyboard(),
    )
    if not is_staff(uid):
        await notify_staff_credit_add(
            ctx.bot, uid, value if isinstance(value, int) else 0, new_credits,
            source="Redeem Code",
            extra=code,
        )
    return True


async def cmd_redeem(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return
    db_user = get_user(update.effective_user.id)
    if not db_user or db_user[5] != 1:
        await rsend(
            update.message,
            style_block(
                ("Bot", "Access Denied"),
                ("Type", "Not Verified"),
                ("Action", "Send /start"),
            ),
        )
        return

    args = ctx.args or []
    if args:
        await _apply_redeem(update, ctx, args[0])
        return ConversationHandler.END

    e_bf = E("6044262726396546853", "🦋")
    e_fn = E("6044146500286550764", "☹️")
    await rsend(
        update.message,
        f"{e_bf} <b>CLAIM REWARD</b>\n\n"
        f"{e_fn} Send your redeem code.\n"
        f"{P[5]} Or use: <code>/redeem YOURCODE</code>\n"
        f"{P[11]} Cancel: /cancel",
    )
    return WAITING_REDEEM_CODE


async def receive_redeem_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return ConversationHandler.END
    code = update.message.text.strip().upper()
    await _apply_redeem(update, ctx, code)
    return ConversationHandler.END


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return ConversationHandler.END
    ctx.user_data["waiting_api_edit"]         = False
    ctx.user_data["editing_api_key"]          = None
    ctx.user_data["waiting_add_admin_id"]     = False
    ctx.user_data["waiting_remove_admin_id"]  = False
    ctx.user_data["waiting_ban_id"]           = False
    ctx.user_data["waiting_unban_id"]         = False
    ctx.user_data["waiting_all_credit_count"]  = False
    ctx.user_data["waiting_all_credit_amount"] = False
    ctx.user_data["all_credit_member_count"]   = None
    ctx.user_data["waiting_minus_id"]          = False
    ctx.user_data["waiting_minus_amount"]      = False
    ctx.user_data["minus_target_id"]           = None
    ctx.user_data["waiting_fk_add"]            = False
    ctx.user_data["waiting_add_link"]          = False
    await rsend(
        update.message,
        style_block(
            ("Bot", "Cancelled"),
            ("Type", "Command Stopped"),
            ("Status", "OK"),
        ),
        reply_markup=main_keyboard(),
    )
    return ConversationHandler.END


async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return
    uid = update.effective_user.id
    if not is_staff(uid):
        await rsend(update.message, denied_block("No permission to use this bot.", uid))
        return
    await rsend(
        update.message,
        style_line("Add Members", "Disabled") + "\n" +
        style_line("Reason", "Bots cannot force-add users") + "\n" +
        style_line("Tip", "Share invite links + join requests") + "\n\n" +
        f"{P[25]} Use Main / Backup / Group invite links from the join menu.\n"
        f"{P[11]} Mass DM invite was removed as requested.",
    )
    return ConversationHandler.END


async def receive_add_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return ConversationHandler.END
    uid = update.effective_user.id
    if not is_staff(uid):
        return ConversationHandler.END

    link = (update.message.text or "").strip()
    low = link.lower()
    if not (
        low.startswith("https://t.me/")
        or low.startswith("http://t.me/")
        or low.startswith("tg://")
        or low.startswith("https://telegram.me/")
        or low.startswith("http://telegram.me/")
    ):
        await rsend(
            update.message,
            f"{P[11]} <b>Invalid link!</b>\n\n"
            f"{P[5]} Please send a valid Telegram invite / channel link.\n"
            f"{P[26]} Example: <code>https://t.me/+AbCdEfGhIjK</code>\n\n"
            f"{P[11]} Cancel: /cancel",
        )
        return WAITING_ADD_LINK

    all_users = get_all_user_ids()
    if not all_users:
        await rsend(
            update.message,
            f"{P[11]} <b>No users found in database.</b>",
        )
        return ConversationHandler.END

    status_msg = await rsend(
        update.message,
        f"{P[19]} <b>Sending invite to all users...</b>\n"
        f"{P[4]} Total: <b>{len(all_users)}</b> | Sent: <b>0</b> | Failed: <b>0</b>",
    )

    invite_text = (
        f"{P[7]} <b>Join Our Channel / Group!</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{P[4]} An admin invited you to join.\n"
        f"{P[3]} Tap the link below to join:\n\n"
        f"{P[29]} <a href=\"{html.escape(link)}\">{html.escape(link)}</a>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{P[8]} See you there!"
    )
    kb = InlineKeyboardMarkup([
        [IKB(
            "Join Now",
            url=link if link.startswith("http") else f"https://t.me/{link.lstrip('@')}",
        )]
    ])

    sent = 0
    failed = 0
    for i, target_id in enumerate(all_users):
        try:
            await bsend(ctx.bot, target_id, invite_text, reply_markup=kb, disable_web_page_preview=False)
            sent += 1
        except Exception:
            failed += 1
        if (i + 1) % 25 == 0:
            try:
                await esend(
                    status_msg,
                    f"{P[19]} <b>Sending invite to all users...</b>\n"
                    f"{P[4]} Total: <b>{len(all_users)}</b> | Sent: <b>{sent}</b> | Failed: <b>{failed}</b>",
                )
            except Exception:
                pass
        await asyncio.sleep(0.05)

    await esend(
        status_msg,
        f"{P[9]} <b>Invite Send Complete!</b>\n\n"
        f"{P[4]} Sent   : <b>{sent}</b>\n"
        f"{P[11]} Failed : <b>{failed}</b>\n"
        f"{P[2]} Total  : <b>{len(all_users)}</b>\n\n"
        f"{P[29]} Link: <code>{html.escape(link)}</code>",
    )
    return ConversationHandler.END


async def cmd_uk(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_staff(uid):
        await rsend(update.message, denied_block("No permission to use this bot.", uid))
        return

    args = ctx.args or []
    if not args or args[0] != "0":
        await rsend(
            update.message,
            f"{P[14]} <b>Usage:</b> Reply to a member with <code>/uk 0</code>\n\n"
            f"{P[22]} This will grant them <b>Lifetime Credits</b>.",
        )
        return

    reply = update.message.reply_to_message
    if reply is None or reply.from_user is None:
        await rsend(
            update.message,
            f"{P[14]} <b>Reply Required</b>\n\n"
            f"{P[22]} Reply to a member's message with <code>/uk 0</code>.",
        )
        return

    target_id = reply.from_user.id
    if not get_user(target_id):
        await rsend(
            update.message,
            f"{P[11]} <b>User Not Found</b>\n\n"
            f"{P[25]} The user must /start and verify the bot first.",
        )
        return

    set_lifetime(target_id, 1)
    await rsend(
        update.message,
        f"{P[10]} <b>Lifetime Credits Activated!</b>\n\n"
        f"{P[48]} User: <code>{target_id}</code>\n"
        f"{P[2]} They will never need credits again.",
    )
    try:
        await bsend(
            ctx.bot, target_id,
            f"{P[10]} <b>Lifetime Credits!</b>\n\n"
            f"{P[2]} You have been granted <b>Lifetime Credits</b>.\n"
            f"{P[9]} You can now use the bot without spending credits.",
            reply_markup=main_keyboard(),
        )
    except Exception:
        pass


async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return
    uid = update.effective_user.id
    if not is_owner(uid):
        await rsend(
            update.message,
            denied_block("No permission to use broadcast.", uid),
        )
        return
    await rsend(
        update.message,
        style_block(
            ("Bot", "Broadcast"),
            ("Type", "Owner Broadcast Mode"),
            ("Action", "Send message now"),
            ("Cancel", "/cancel"),
            ("Tip", "Album 2 to 5 photos OK"),
        ),
    )
    return WAITING_BROADCAST_MSG


async def receive_broadcast_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return ConversationHandler.END
    uid = update.effective_user.id
    if not is_owner(uid):
        return ConversationHandler.END

    ctx.user_data["broadcast_chat_id"] = update.effective_chat.id
    ctx.user_data["broadcast_msg_id"]  = update.message.message_id
    ctx.user_data["broadcast_button"]  = None
    ctx.user_data["broadcast_comment"] = None
    ctx.user_data["broadcast_media_group_id"] = update.message.media_group_id
    ctx.user_data["broadcast_msg_ids"] = [update.message.message_id]
    if update.message.media_group_id:
        # Telegram delivers album items as separate updates. Give the queue a moment
        # before taking the initial snapshot so broadcast does not race the album.
        await asyncio.sleep(1.2)
        buf = ctx.user_data.setdefault("mg_buffer", {})
        gid = update.message.media_group_id
        buf.setdefault(gid, [])
        if update.message.message_id not in buf[gid]:
            buf[gid].append(update.message.message_id)
        ctx.user_data["broadcast_msg_ids"] = list(buf[gid])

    kb = InlineKeyboardMarkup([
        [
            IKB("Add Comment", callback_data="bc_add_comment", style="primary", icon_custom_emoji_id="5443038326535759644"),
            IKB("Add Button", callback_data="bc_add_button", style="primary", icon_custom_emoji_id="5278327121008167894"),
        ],
        [
            IKB("Skip (Start Now)", callback_data="bc_skip", style="success", icon_custom_emoji_id="5445365692004071819"),
        ]
    ])
    await rsend(
        update.message,
        f"{P[9]} <b>Message received!</b>\n\n"
        f"{P[17]} Optional: add a <b>comment</b> and/or an <b>inline button</b>.\n\n"
        f"{P[4]} Tap <b>Add Comment</b>, <b>Add Button</b>, or <b>Skip (Start Now)</b>.",
        reply_markup=kb,
    )
    return WAITING_BROADCAST_BTN_CHOICE


async def receive_broadcast_comment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return ConversationHandler.END
    uid = update.effective_user.id
    if not is_owner(uid):
        return ConversationHandler.END

    raw = (update.message.text or "").strip()
    if raw.lower() == "skip":
        ctx.user_data["broadcast_comment"] = None
        note = "No comment"
    else:
        ctx.user_data["broadcast_comment"] = raw
        note = f"Comment saved: <code>{html.escape(raw[:200])}</code>"

    kb = InlineKeyboardMarkup([
        [
            IKB("Add Button", callback_data="bc_add_button", style="primary", icon_custom_emoji_id="5278327121008167894"),
            IKB("Skip (Start Now)", callback_data="bc_skip", style="success", icon_custom_emoji_id="5445365692004071819"),
        ]
    ])
    await rsend(
        update.message,
        f"{P[9]} <b>{note}</b>\n\n"
        f"{P[17]} Add an inline button, or start now.\n\n"
        f"{P[4]} Tap <b>Add Button</b> or <b>Skip (Start Now)</b>.",
        reply_markup=kb,
    )
    return WAITING_BROADCAST_BTN_CHOICE


async def _broadcast_copy_with_retry(bot, target_id: int, source_chat_id: int, message_id: int, reply_markup=None):
    """Copy a broadcast message with basic Telegram flood-control retries."""
    last_error = None
    for attempt in range(4):
        try:
            return await bot.copy_message(
                chat_id=target_id,
                from_chat_id=source_chat_id,
                message_id=message_id,
                reply_markup=reply_markup,
            )
        except Exception as exc:
            last_error = exc
            # Some Telegram message types/clients reject copy_message; forwarding is a safe fallback.
            if attempt == 0:
                try:
                    return await bot.forward_message(
                        chat_id=target_id,
                        from_chat_id=source_chat_id,
                        message_id=message_id,
                    )
                except Exception as forward_exc:
                    last_error = forward_exc
            retry_after = getattr(exc, "retry_after", None)
            if retry_after is None:
                # python-telegram-bot may expose the value under parameters.
                params = getattr(exc, "parameters", None)
                retry_after = getattr(params, "retry_after", None) if params else None
            if retry_after is None:
                raise
            await asyncio.sleep(min(max(float(retry_after), 1.0), 30.0))
    if last_error:
        raise last_error


async def _do_broadcast(bot, update_or_msg, source_chat_id: int, source_msg_id: int, button_markup=None, broadcaster_uid: int = None, comment: str = None, source_msg_ids: list = None):
    all_users = get_all_user_ids()
    if not all_users:
        await rsend(
            update_or_msg,
            style_block(
                ("Bot", "Broadcast"),
                ("Type", "No Users"),
                ("Status", "Nothing to send"),
            ),
        )
        return

    broadcast_id = create_broadcast_log(broadcaster_uid or 0, f"{source_chat_id}/{source_msg_id}")

    msg_ids = source_msg_ids if source_msg_ids else [source_msg_id]
    seen = set()
    msg_ids = [m for m in msg_ids if not (m in seen or seen.add(m))]

    sent = 0
    failed = 0

    status_msg = await rsend(
        update_or_msg,
        style_block(
            ("Bot", "Broadcasting"),
            ("Total", str(len(all_users))),
            ("Sent", "0"),
            ("Failed", "0"),
        ),
        reply_markup=broadcast_stop_keyboard(),
    )

    async def _loop():
        nonlocal sent, failed
        try:
            for i, target_id in enumerate(all_users):
                try:
                    if len(msg_ids) > 1:
                        first_copied = None
                        copied_count = 0
                        for mid in msg_ids:
                            m = await _broadcast_copy_with_retry(
                                bot, target_id, source_chat_id, mid,
                                reply_markup=button_markup if mid == msg_ids[-1] else None,
                            )
                            copied_count += 1
                            try:
                                save_broadcast_delivery(broadcast_id, target_id, m.message_id)
                            except Exception:
                                pass
                            if first_copied is None:
                                first_copied = m
                        if copied_count != len(msg_ids):
                            raise RuntimeError("Incomplete album delivery")
                        if first_copied is not None:
                            try:
                                await bot.pin_chat_message(chat_id=target_id, message_id=first_copied.message_id, disable_notification=True)
                            except Exception:
                                pass
                    else:
                        copied = await _broadcast_copy_with_retry(
                            bot,
                            target_id,
                            source_chat_id,
                            msg_ids[0],
                            button_markup=button_markup,
                        )
                        try:
                            save_broadcast_delivery(broadcast_id, target_id, copied.message_id)
                        except Exception:
                            pass
                        try:
                            await bot.pin_chat_message(
                                chat_id=target_id,
                                message_id=copied.message_id,
                                disable_notification=True,
                            )
                        except Exception:
                            pass
                    if comment:
                        try:
                            await bot.send_message(chat_id=target_id, text=comment)
                        except Exception:
                            pass
                    sent += 1
                except Exception as exc:
                    failed += 1
                    print(f"Broadcast delivery failed user={target_id}: {type(exc).__name__}: {exc}")

                if (i + 1) % 5 == 0 or (i + 1) == len(all_users):
                    try:
                        await esend(
                            status_msg,
                            style_block(
                                ("Bot", "Broadcasting"),
                                ("Total", str(len(all_users))),
                                ("Sent", str(sent)),
                                ("Failed", str(failed)),
                            ),
                            reply_markup=broadcast_stop_keyboard(),
                        )
                    except Exception:
                        pass
                await asyncio.sleep(0.08)

            try:
                await esend(
                    status_msg,
                    style_block(
                        ("Bot", "Broadcast Complete"),
                        ("Sent", str(sent)),
                        ("Failed", str(failed)),
                        ("Total", str(len(all_users))),
                    ),
                )
            except Exception:
                pass
        except asyncio.CancelledError:
            try:
                await esend(
                    status_msg,
                    style_block(
                        ("Bot", "Broadcast Stopped"),
                        ("Sent", str(sent)),
                        ("Failed", str(failed)),
                        ("At", f"{sent + failed}/{len(all_users)}"),
                    ),
                )
            except Exception:
                pass
            raise
        finally:
            if broadcaster_uid:
                ACTIVE_BROADCAST_TASKS.pop(broadcaster_uid, None)

    task = asyncio.create_task(_loop())
    if broadcaster_uid:
        ACTIVE_BROADCAST_TASKS[broadcaster_uid] = task


async def cb_broadcast_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if not is_owner(uid):
        await query.answer("Not authorized.", show_alert=True)
        return ConversationHandler.END

    if query.data == "bc_skip":
        source_chat_id = ctx.user_data.get("broadcast_chat_id")
        source_msg_id  = ctx.user_data.get("broadcast_msg_id")
        source_msg_ids = ctx.user_data.get("broadcast_msg_ids") or [source_msg_id]
        comment = ctx.user_data.get("broadcast_comment")
        try:
            await query.message.delete()
        except Exception:
            pass
        await _do_broadcast(
            ctx.bot, query.message, source_chat_id, source_msg_id,
            button_markup=None, broadcaster_uid=uid,
            comment=comment, source_msg_ids=source_msg_ids,
        )
        return ConversationHandler.END

    if query.data == "bc_add_comment":
        try:
            await query.message.delete()
        except Exception:
            pass
        await ctx.bot.send_message(
            chat_id=uid,
            text=(
                f"{P[34]} <b>Add Broadcast Comment</b>\n\n"
                f"{P[22]} Send the comment text to send with the broadcast.\n"
                f"{P[5]} Or send <code>skip</code> for no comment.\n\n"
                f"{P[11]} Cancel: /cancel"
            ),
            parse_mode="HTML",
        )
        return WAITING_BROADCAST_COMMENT

    if query.data == "bc_add_button":
        try:
            await query.message.delete()
        except Exception:
            pass
        await ctx.bot.send_message(
            chat_id=uid,
            text=(
                f"{P[7]} <b>Add Inline Button</b>\n\n"
                f"{P[22]} Send the <b>URL / link</b> for the button.\n"
                f"{P[5]} Example: <code>https://t.me/yourchannel</code>\n\n"
                f"{P[4]} After you send the link, broadcast starts immediately.\n"
                f"Every user will see the button and tapping it opens the link.\n\n"
                f"{P[11]} Cancel: /cancel"
            ),
            parse_mode="HTML",
        )
        return WAITING_BROADCAST_BTN_URL

    return WAITING_BROADCAST_BTN_CHOICE


async def receive_broadcast_btn_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return ConversationHandler.END
    uid = update.effective_user.id
    if not is_owner(uid):
        return ConversationHandler.END

    url = update.message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
        await rsend(
            update.message,
            f"{P[11]} <b>Invalid URL!</b>\n\n"
            f"{P[5]} Please send a valid link starting with <code>https://</code> or <code>tg://</code>.\n"
            f"{P[11]} Cancel: /cancel",
        )
        return WAITING_BROADCAST_BTN_URL

    ctx.user_data["broadcast_btn_url"] = url
    await rsend(
        update.message,
        f"{P[18]} <b>Button Text</b>\n\n"
        f"{P[22]} Send the text for the button.\n"
        f"{P[5]} Example: <code>Open Channel</code>\n\n"
        f"{P[11]} Cancel: /cancel",
    )
    return WAITING_BROADCAST_BTN_TEXT


async def receive_broadcast_btn_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return ConversationHandler.END
    uid = update.effective_user.id
    if not is_owner(uid):
        return ConversationHandler.END

    btn_text = update.message.text.strip()
    if not btn_text:
        await rsend(update.message, f"{P[11]} Button text cannot be empty. Please try again.")
        return WAITING_BROADCAST_BTN_TEXT

    btn_url = ctx.user_data.get("broadcast_btn_url") or ctx.user_data.get("broadcast_btn_url", "")
    if not btn_url:
        await rsend(
            update.message,
            f"{P[11]} Button URL missing. Send /broadcast again.",
        )
        return ConversationHandler.END

    button_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(text=btn_text, url=btn_url)]
    ])
    source_chat_id = ctx.user_data.get("broadcast_chat_id")
    source_msg_id  = ctx.user_data.get("broadcast_msg_id")
    source_msg_ids = ctx.user_data.get("broadcast_msg_ids") or [source_msg_id]
    comment = ctx.user_data.get("broadcast_comment")

    await rsend(
        update.message,
        f"{P[9]} <b>Starting broadcast with button...</b>\n"
        f"{P[17]} Button: <b>{html.escape(btn_text)}</b>\n"
        f"{P[7]} URL: <code>{html.escape(btn_url)}</code>",
    )
    await _do_broadcast(
        ctx.bot, update.message, source_chat_id, source_msg_id,
        button_markup=button_markup, broadcaster_uid=uid,
        comment=comment, source_msg_ids=source_msg_ids,
    )
    return ConversationHandler.END


async def receive_broadcast_btn_emoji(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_private(update):
        return ConversationHandler.END
    uid = update.effective_user.id
    if not is_owner(uid):
        return ConversationHandler.END

    raw = update.message.text.strip()
    btn_text = ctx.user_data.get("broadcast_btn_text", "Click Here")
    btn_url  = ctx.user_data.get("broadcast_btn_url", "")

    if raw.lower() == "skip":
        final_text = btn_text
    elif raw.isdigit():
        emoji_html = f'<tg-emoji emoji-id="{raw}">⭐</tg-emoji>'
        final_text = f"{emoji_html} {btn_text}"
    else:
        await rsend(
            update.message,
            f"{P[11]} <b>Invalid Emoji ID!</b>\n\n"
            f"{P[5]} Please send a valid numeric emoji ID or <code>skip</code>.",
        )
        return WAITING_BROADCAST_BTN_EMOJI

    plain_btn_text = btn_text if raw.lower() == "skip" else btn_text
    button_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(text=plain_btn_text, url=btn_url)]
    ])

    source_chat_id = ctx.user_data.get("broadcast_chat_id")
    source_msg_id  = ctx.user_data.get("broadcast_msg_id")

    await rsend(
        update.message,
        f"{P[9]} <b>Starting broadcast with button...</b>\n"
        f"{P[17]} Button: <b>{html.escape(plain_btn_text)}</b>\n"
        f"{P[7]} URL: <code>{html.escape(btn_url)}</code>",
    )
    await _do_broadcast(ctx.bot, update.message, source_chat_id, source_msg_id, button_markup=button_markup, broadcaster_uid=uid, comment=ctx.user_data.get('broadcast_comment'), source_msg_ids=ctx.user_data.get('broadcast_msg_ids') or [source_msg_id])
    return ConversationHandler.END


async def cb_broadcast_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if not is_staff(uid):
        await query.answer("Not authorized.", show_alert=True)
        return
    task = ACTIVE_BROADCAST_TASKS.get(uid)
    if not task or task.done():
        await query.answer("No active broadcast running.", show_alert=True)
        return
    task.cancel()
    await query.answer("⛔ Broadcast stopped!", show_alert=True)


# ═══════════════════════════════════════════════════
#        JOIN REQUEST AUTO-APPROVE HANDLER
# ═══════════════════════════════════════════════════

async def auto_approve_join_request(bot, user_id: int, chat_id):
    await asyncio.sleep(10)
    try:
        await bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
    except Exception:
        pass
    try:
        await asyncio.sleep(2)
        ok = await _check_chat_member(bot, chat_id, user_id)
        if ok is True and str(chat_id) != get_setting("third_channel_id"):
            remove_join_request(user_id, str(chat_id))
    except Exception:
        pass


async def cb_join_request(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    req: ChatJoinRequest = update.chat_join_request
    if req is None:
        return

    chat_id  = req.chat.id
    user_id  = req.from_user.id
    chat_type = getattr(req.chat, "type", "") or ""
    cid = str(chat_id)

    # Learn the private channel ID from its join-request event, without confusing it
    # with the existing main/backup channels.
    if chat_type == "channel" and cid not in {get_setting("main_channel_id"), get_setting("backup_channel_id")} and not get_setting("third_channel_id"):
        set_setting("third_channel_id", cid)
    _store_chat_id_from_event(chat_id, chat_type)

    add_join_request(user_id, cid)

    asyncio.create_task(auto_approve_join_request(ctx.bot, user_id, chat_id))


async def cb_my_chat_member(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    mcm = update.my_chat_member
    if mcm is None:
        return
    chat = mcm.chat
    if chat is None:
        return
    new_status = getattr(mcm.new_chat_member, "status", "") or ""
    if new_status in ("administrator", "member", "restricted"):
        _store_chat_id_from_event(chat.id, getattr(chat, "type", "") or "")


async def cb_chat_member(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cm = update.chat_member
    if cm is None:
        return
    chat = cm.chat
    user = cm.new_chat_member.user if cm.new_chat_member else None
    if chat is None or user is None or user.is_bot:
        return
    new_status = getattr(cm.new_chat_member, "status", "") or ""
    old_status = getattr(cm.old_chat_member, "status", "") or ""
    cid = str(chat.id)
    _store_chat_id_from_event(chat.id, getattr(chat, "type", "") or "")
    if new_status in ("member", "administrator", "restricted") and old_status in (
        "left", "kicked", "banned", "chat_member_status_left", ""
    ):
        add_join_request(user.id, cid)
    elif new_status in ("left", "kicked", "banned"):
        remove_join_request(user.id, cid)


# ═══════════════════════════════════════════════════
#                     MAIN
# ═══════════════════════════════════════════════════

def unban_all_users_on_start():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM banned_users")
        conn.commit()
        print(f"Unbanned all users on start (cleared bans).")
    except Exception as e:
        print(f"unban_all error: {e}")
    finally:
        conn.close()


def ensure_staff_credits_on_start():
    try:
        for oid in OWNER_IDS:
            try:
                if get_user(oid):
                    set_credits(oid, OWNER_CREDITS)
                    print(f"Owner {oid} credits set to huge value.")
                else:
                    create_user(oid, "owner")
                    set_credits(oid, OWNER_CREDITS)
                    set_verified(oid)
                    print(f"Owner {oid} created + credits set.")
            except Exception as e:
                print(f"Owner {oid} setup error: {e}")
        for aid in ADMIN_IDS:
            try:
                if get_user(aid):
                    set_credits(aid, ADMIN_CREDITS)
                    print(f"Admin {aid} credits set.")
                else:
                    create_user(aid, "admin")
                    set_credits(aid, ADMIN_CREDITS)
                    set_verified(aid)
                    print(f"Admin {aid} created + credits set.")
            except Exception as e:
                print(f"Admin {aid} setup error: {e}")
        for aid in get_dynamic_admins():
            try:
                if get_user(aid):
                    set_credits(aid, ADMIN_CREDITS)
            except Exception:
                pass
    except Exception as e:
        print(f"ensure_staff_credits_on_start error: {e}")


def ensure_all_users_min_credits():
    try:
        staff_ids = set(get_all_staff_ids())
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT telegram_id, credits, COALESCE(lifetime,0) FROM users")
        rows = c.fetchall()
        fixed = 0
        for tid, creds, life in rows:
            if tid in staff_ids or life:
                continue
            if creds == 5000:
                c.execute("UPDATE users SET credits = ? WHERE telegram_id = ?", (START_USER_CREDITS, tid))
                fixed += 1
        conn.commit()
        conn.close()
        if fixed:
            print(f"Normalized legacy 5000-credit balances to {START_USER_CREDITS} for {fixed} users.")
    except Exception as e:
        print(f"ensure_all_users_min_credits skip: {e}")


def clamp_overlimit_users_on_start():
    staff_ids = set(get_all_staff_ids())
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT telegram_id, credits, COALESCE(lifetime,0) FROM users")
    rows = c.fetchall()
    zeroed = 0
    for tid, creds, life in rows:
        if tid in staff_ids or life:
            continue
        if creds > MAX_USER_CREDITS:
            c.execute("UPDATE users SET credits = 0 WHERE telegram_id = ?", (tid,))
            zeroed += 1
    conn.commit()
    conn.close()
    if zeroed:
        print(f"Zeroed {zeroed} users over {MAX_USER_CREDITS} credits.")


def _build_full_app(token: str) -> Application:
    # Longer HTTP timeouts help when Telegram's API responds slowly.
    request = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=10.0,
    )
    get_updates_request = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=40.0,
        write_timeout=30.0,
        pool_timeout=10.0,
    )
    app = (
        Application.builder()
        .token(token)
        .request(request)
        .get_updates_request(get_updates_request)
        .concurrent_updates(True)
        .build()
    )

    redeem_conv = ConversationHandler(
        entry_points=[CommandHandler("redeem", cmd_redeem)],
        states={
            WAITING_REDEEM_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_redeem_code)
            ]
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_chat=True,
    )

    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", cmd_broadcast)],
        states={
            WAITING_BROADCAST_MSG: [
                MessageHandler(~filters.COMMAND, receive_broadcast_msg)
            ],
            WAITING_BROADCAST_BTN_CHOICE: [
                CallbackQueryHandler(cb_broadcast_choice, pattern="^bc_(add_button|add_comment|skip)$")
            ],
            WAITING_BROADCAST_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broadcast_comment)
            ],
            WAITING_BROADCAST_BTN_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broadcast_btn_url)
            ],
            WAITING_BROADCAST_BTN_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broadcast_btn_text)
            ],
            WAITING_BROADCAST_BTN_EMOJI: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broadcast_btn_emoji)
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_chat=True,
    )

    add_conv = ConversationHandler(
        entry_points=[CommandHandler("add", cmd_add)],
        states={
            WAITING_ADD_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_link)
            ]
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_chat=True,
    )

    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("stats",       cmd_stats))
    app.add_handler(CommandHandler("create",      cmd_create))
    app.add_handler(CommandHandler("addcredits",  cmd_addcredits))
    app.add_handler(CommandHandler("le",          cmd_le))
    app.add_handler(CommandHandler("uk",          cmd_uk))
    app.add_handler(CommandHandler("panel",       cmd_panel))
    app.add_handler(CommandHandler("setids",      cmd_setids))
    app.add_handler(CommandHandler("ban",         cmd_ban))
    app.add_handler(CommandHandler("unban",       cmd_unban))
    app.add_handler(redeem_conv)
    app.add_handler(broadcast_conv)
    app.add_handler(add_conv)

    app.add_handler(CallbackQueryHandler(
        cb_credit_review,
        pattern=r"^credit_(ban|reject)\|",
    ))

    app.add_handler(CallbackQueryHandler(
        cb_admin_panel,
        pattern=(
            r"^("
            r"admin_buttons|admin_apis|back_admin|"
            r"admin_filter_keys|fk_add|"
            r"admin_all_credit|admin_minus_credit|"
            r"toggle_btn_num|toggle_btn_tg|toggle_btn_aadhar|toggle_btn_refer|"
            r"toggle_btn_balance|toggle_btn_vehicle|toggle_btn_pan|toggle_btn_mobile|"
            r"toggle_bot_status|toggle_group_status|"
            r"admin_ban_user|admin_unban_user|admin_remove_broadcast|admin_download_db|"
            r"admin_add_admin|admin_remove_admin|"
            r"edit_api_num|edit_api_tg|edit_api_aadhar|edit_api_vehicle|edit_api_pan|edit_api_mobile|"
            r"delete_api_num|delete_api_tg|delete_api_aadhar|delete_api_vehicle|delete_api_pan|delete_api_mobile"
            r")$"
        )
    ))
    app.add_handler(CallbackQueryHandler(
        cb_admin_panel,
        pattern=r"^fk_del\|.+$",
    ))
    app.add_handler(CallbackQueryHandler(
        cb_admin_panel,
        pattern=r"^bc_del\|\d+$",
    ))
    app.add_handler(CallbackQueryHandler(cb_verify, pattern="^verify$"))
    app.add_handler(CallbackQueryHandler(cb_broadcast_stop, pattern="^broadcast_stop$"))
    app.add_handler(ChatJoinRequestHandler(cb_join_request))
    app.add_handler(ChatMemberHandler(cb_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(cb_chat_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.ChatType.PRIVATE | filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
        handle_text
    ))
    return app


def main():
    token = os.getenv("BOT_TOKEN", BOT_TOKEN).strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is missing. Set BOT_TOKEN in Railway environment variables.")
    init_db()
    unban_all_users_on_start()
    ensure_staff_credits_on_start()
    ensure_all_users_min_credits()
    clamp_overlimit_users_on_start()

    app = _build_full_app(token)
    print("Bot running → @UKRAINEBSTBOT")
    print(f"  Number API → ukraine-numinfoapi.vercel.app")
    print(f"  Verification: YouTube channel button + Verify button")
    app.run_polling(
        drop_pending_updates=True,
        bootstrap_retries=-1,  # Keep retrying if Telegram is temporarily unreachable.
        allowed_updates=[
            "message",
            "callback_query",
            "chat_join_request",
            "chat_member",
            "my_chat_member",
            "channel_post",
            "edited_message",
        ],
    )


if __name__ == "__main__":
    main()