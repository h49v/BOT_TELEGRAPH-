import re
import os
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ─── Permission Check ─────────────────────────────────────
async def is_admin(user_id: int) -> bool:
    from database.db import get_admin
    return await get_admin(user_id) is not None

async def is_main_admin(user_id: int) -> bool:
    from database.db import get_admin
    admin = await get_admin(user_id)
    return admin is not None and admin[2] == "main"

# ─── Group ID Extractor (Bot API) ─────────────────────────
async def extract_group_id(bot: Bot, link_or_id: str) -> tuple:
    link_or_id = link_or_id.strip()

    if re.match(r"^-?\d+$", link_or_id):
        try:
            chat = await bot.get_chat(int(link_or_id))
            return chat.id, chat.title or str(chat.id)
        except Exception as e:
            return None, f"❌ فشل جلب المجموعة: {e}"

    if link_or_id.startswith("@"):
        try:
            chat = await bot.get_chat(link_or_id)
            return chat.id, chat.title or link_or_id
        except Exception as e:
            return None, f"❌ فشل جلب المجموعة: {e}"

    match_username = re.search(r"t\.me/([a-zA-Z0-9_]+)$", link_or_id)
    if match_username:
        username = "@" + match_username.group(1)
        try:
            chat = await bot.get_chat(username)
            return chat.id, chat.title or username
        except Exception as e:
            return None, f"❌ فشل جلب المجموعة: {e}"

    match_invite = re.search(r"t\.me/\+([a-zA-Z0-9_-]+)", link_or_id)
    if match_invite:
        return None, (
            "⚠️ روابط الدعوة الخاصة تحتاج Userbot.\n"
            "استخدم زر «إضافة كروب عبر Userbot» بدلاً من هذا."
        )

    return None, "❌ صيغة غير معروفة. أرسل ID مباشر أو @username أو رابط t.me/username"

# ─── Keyboards ────────────────────────────────────────────
def main_menu_keyboard(is_main: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📋 إدارة الكروبات",      callback_data="manage_groups")],
        [InlineKeyboardButton(text="📱 جلسة Userbot",        callback_data="sessions_menu")],
        [InlineKeyboardButton(text="📢 النشر والبث",          callback_data="broadcast_menu")],
        [InlineKeyboardButton(text="🧩 القوالب",             callback_data="templates_menu")],
        [InlineKeyboardButton(text="🤖 الردود التلقائية",    callback_data="autoreplies_menu")],
        [InlineKeyboardButton(text="⏰ الجدولة",             callback_data="schedule_menu")],
        [InlineKeyboardButton(text="📊 الإحصائيات",          callback_data="stats_menu")],
        [InlineKeyboardButton(text="🚫 القائمة السوداء",      callback_data="blacklist_menu")],
        [InlineKeyboardButton(text="💾 النسخ الاحتياطي",     callback_data="backup_menu")],
    ]
    if is_main:
        buttons.append([InlineKeyboardButton(text="👥 إدارة المشرفين", callback_data="admins_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def back_button(callback: str = "main_menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 رجوع", callback_data=callback)]
    ])

def confirm_keyboard(yes_cb: str, no_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ نعم", callback_data=yes_cb),
            InlineKeyboardButton(text="❌ لا",  callback_data=no_cb),
        ]
    ])

# ─── Parse Inline Buttons from Text ──────────────────────
def parse_buttons(buttons_text: str) -> InlineKeyboardMarkup | None:
    if not buttons_text:
        return None
    rows = []
    for line in buttons_text.strip().split("\n"):
        row = []
        for item in line.split(","):
            item = item.strip()
            if "|" in item:
                text, url = item.split("|", 1)
                row.append(InlineKeyboardButton(text=text.strip(), url=url.strip()))
        if row:
            rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

# ─── Format Helpers ───────────────────────────────────────
def escape_md(text: str) -> str:
    chars = r"_*[]()~`>#+-=|{}.!"
    for c in chars:
        text = text.replace(c, f"\\{c}")
    return text

def format_group_list(groups: list) -> str:
    if not groups:
        return "📭 لا توجد كروبات مضافة"
    lines = []
    for i, g in enumerate(groups, 1):
        status = "✅" if g[2] else "⛔"
        lines.append(f"{i}. {status} <b>{g[1]}</b>\n   <code>{g[0]}</code>")
    return "\n\n".join(lines)
