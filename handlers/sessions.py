"""
handlers/sessions.py
إدارة جلسات Telethon (Userbot)
استخراج الجلسة + إضافة الكروبات عبر Userbot
"""

import asyncio
import os
import re
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.helpers import is_admin, is_main_admin, back_button
from database.db import (
    save_session, get_session, delete_session,
    add_group, get_all_groups
)

logger = logging.getLogger(__name__)
router = Router()

# ─── States ───────────────────────────────────────────────
class SessionStates(StatesGroup):
    waiting_phone     = State()
    waiting_code      = State()
    waiting_password  = State()
    waiting_group_id  = State()   # إضافة كروب عبر زر

# ─── Helper: get Telethon client ──────────────────────────
def _get_client(session_string: str = None):
    """
    يرجع TelegramClient.
    session_string=None → StringSession جديدة (لتسجيل الدخول)
    session_string=str  → استئناف جلسة محفوظة
    """
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        return None

    api_id   = int(os.environ.get("API_ID", 0))
    api_hash = os.environ.get("API_HASH", "")
    if not api_id or not api_hash:
        return None

    session = StringSession(session_string or "")
    return TelegramClient(session, api_id, api_hash)

# ─── Keyboards ────────────────────────────────────────────
def sessions_keyboard(has_session: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_session:
        rows += [
            [InlineKeyboardButton(text="📋 عرض الجلسة الحالية",   callback_data="session_view")],
            [InlineKeyboardButton(text="➕ إضافة كروب عبر Userbot", callback_data="session_add_group")],
            [InlineKeyboardButton(text="🔄 تحديث الجلسة",          callback_data="session_new")],
            [InlineKeyboardButton(text="🗑 حذف الجلسة",            callback_data="session_delete")],
        ]
    else:
        rows += [
            [InlineKeyboardButton(text="🔑 استخراج جلسة جديدة", callback_data="session_new")],
        ]
    rows.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def cancel_keyboard(back_cb: str = "sessions_menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ إلغاء", callback_data=back_cb)]
    ])

# ─── Entry: sessions_menu ─────────────────────────────────
@router.callback_query(F.data == "sessions_menu")
async def cb_sessions_menu(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    session_row = await get_session()
    has = session_row is not None
    status = "✅ جلسة نشطة محفوظة" if has else "❌ لا توجد جلسة"
    await cb.message.edit_text(
        f"📱 <b>إدارة جلسة Userbot</b>\n\n"
        f"الحالة: {status}\n\n"
        "الجلسة تُستخدم لإضافة الكروبات تلقائياً\n"
        "وجلب IDs المجموعات الخاصة.",
        reply_markup=sessions_keyboard(has),
        parse_mode="HTML"
    )

# ─── View Session ─────────────────────────────────────────
@router.callback_query(F.data == "session_view")
async def cb_session_view(cb: CallbackQuery):
    if not await is_main_admin(cb.from_user.id):
        await cb.answer("⛔ للمشرف الرئيسي فقط.", show_alert=True)
        return
    row = await get_session()
    if not row:
        await cb.answer("لا توجد جلسة محفوظة.", show_alert=True)
        return
    session_str = row[0]
    # أظهر أول وآخر 10 أحرف فقط للأمان
    preview = f"{session_str[:10]}...{session_str[-10:]}" if len(session_str) > 25 else session_str
    await cb.message.edit_text(
        f"📋 <b>الجلسة المحفوظة</b>\n\n"
        f"<code>{preview}</code>\n\n"
        "⚠️ لا تشارك الجلسة مع أحد — تمنح وصولاً كاملاً للحساب.",
        reply_markup=back_button("sessions_menu"),
        parse_mode="HTML"
    )

# ─── Delete Session ───────────────────────────────────────
@router.callback_query(F.data == "session_delete")
async def cb_session_delete(cb: CallbackQuery):
    if not await is_main_admin(cb.from_user.id):
        await cb.answer("⛔ للمشرف الرئيسي فقط.", show_alert=True)
        return
    await delete_session()
    await cb.answer("✅ تم حذف الجلسة.", show_alert=True)
    await cb.message.edit_text(
        "📱 <b>إدارة جلسة Userbot</b>\n\nالحالة: ❌ لا توجد جلسة",
        reply_markup=sessions_keyboard(False),
        parse_mode="HTML"
    )

# ─── New Session: Step 1 — Phone ──────────────────────────
@router.callback_query(F.data == "session_new")
async def cb_session_new(cb: CallbackQuery, state: FSMContext):
    if not await is_main_admin(cb.from_user.id):
        await cb.answer("⛔ للمشرف الرئيسي فقط.", show_alert=True)
        return

    api_id   = os.environ.get("API_ID", "")
    api_hash = os.environ.get("API_HASH", "")
    if not api_id or not api_hash:
        await cb.answer(
            "❌ API_ID و API_HASH غير مضبوطين في .env",
            show_alert=True
        )
        return

    await state.set_state(SessionStates.waiting_phone)
    await cb.message.edit_text(
        "📱 <b>استخراج جلسة Telethon</b>\n\n"
        "أرسل رقم هاتفك بالصيغة الدولية:\n"
        "<code>+9665xxxxxxxx</code>\n\n"
        "سيصلك كود تحقق على تيليجرام.",
        reply_markup=cancel_keyboard("sessions_menu"),
        parse_mode="HTML"
    )

@router.message(SessionStates.waiting_phone)
async def process_phone(msg: Message, state: FSMContext):
    phone = msg.text.strip()
    if not re.match(r"^\+\d{7,15}$", phone):
        await msg.answer(
            "❌ رقم غير صحيح. مثال: <code>+9665xxxxxxxx</code>",
            reply_markup=cancel_keyboard("sessions_menu"),
            parse_mode="HTML"
        )
        return

    client = _get_client()
    if client is None:
        await msg.answer("❌ Telethon غير مثبت أو API_ID/API_HASH ناقص.")
        await state.clear()
        return

    status_msg = await msg.answer("⏳ جاري الاتصال...")
    try:
        await client.connect()
        result = await client.send_code_request(phone)
        await state.update_data(
            phone=phone,
            phone_code_hash=result.phone_code_hash,
            client_session=client.session.save()
        )
        await state.set_state(SessionStates.waiting_code)
        await status_msg.edit_text(
            "✅ تم إرسال كود التحقق.\n\n"
            "أرسل الكود المكون من 5 أرقام:\n"
            "<code>1 2 3 4 5</code> ← بدون مسافات",
            reply_markup=cancel_keyboard("sessions_menu"),
            parse_mode="HTML"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ خطأ: <code>{e}</code>", parse_mode="HTML")
        await state.clear()
    finally:
        await client.disconnect()

# ─── New Session: Step 2 — Code ───────────────────────────
@router.message(SessionStates.waiting_code)
async def process_code(msg: Message, state: FSMContext):
    code = msg.text.strip().replace(" ", "")
    data = await state.get_data()
    phone           = data["phone"]
    phone_code_hash = data["phone_code_hash"]
    saved_session   = data["client_session"]

    client = _get_client(saved_session)
    if client is None:
        await msg.answer("❌ خطأ في إنشاء العميل.")
        await state.clear()
        return

    status_msg = await msg.answer("⏳ جاري التحقق...")
    try:
        await client.connect()
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        session_str = client.session.save()
        await save_session(session_str)
        await state.clear()
        await status_msg.edit_text(
            "✅ <b>تم تسجيل الدخول بنجاح!</b>\n"
            "الجلسة محفوظة في قاعدة البيانات.",
            reply_markup=sessions_keyboard(True),
            parse_mode="HTML"
        )
    except Exception as e:
        err = str(e)
        if "Two-steps" in err or "password" in err.lower() or "2FA" in err:
            await state.update_data(client_session=client.session.save())
            await state.set_state(SessionStates.waiting_password)
            await status_msg.edit_text(
                "🔐 حسابك محمي بكلمة مرور ثنائية.\n"
                "أرسل كلمة المرور:",
                reply_markup=cancel_keyboard("sessions_menu"),
                parse_mode="HTML"
            )
        else:
            await status_msg.edit_text(
                f"❌ فشل التحقق: <code>{e}</code>",
                parse_mode="HTML"
            )
            await state.clear()
    finally:
        await client.disconnect()

# ─── New Session: Step 3 — 2FA Password ───────────────────
@router.message(SessionStates.waiting_password)
async def process_password(msg: Message, state: FSMContext):
    password    = msg.text.strip()
    data        = await state.get_data()
    saved_session = data["client_session"]

    # احذف رسالة كلمة المرور فوراً للأمان
    try:
        await msg.delete()
    except Exception:
        pass

    client = _get_client(saved_session)
    if client is None:
        await msg.answer("❌ خطأ في إنشاء العميل.")
        await state.clear()
        return

    status_msg = await msg.answer("⏳ جاري التحقق من كلمة المرور...")
    try:
        await client.connect()
        await client.sign_in(password=password)
        session_str = client.session.save()
        await save_session(session_str)
        await state.clear()
        await status_msg.edit_text(
            "✅ <b>تم تسجيل الدخول بنجاح!</b>\n"
            "الجلسة محفوظة.",
            reply_markup=sessions_keyboard(True),
            parse_mode="HTML"
        )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ كلمة المرور خاطئة: <code>{e}</code>",
            parse_mode="HTML"
        )
        await state.clear()
    finally:
        await client.disconnect()

# ─── Add Group via Userbot ────────────────────────────────
@router.callback_query(F.data == "session_add_group")
async def cb_session_add_group(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    row = await get_session()
    if not row:
        await cb.answer("❌ لا توجد جلسة Userbot. استخرج جلسة أولاً.", show_alert=True)
        return
    await state.set_state(SessionStates.waiting_group_id)
    await cb.message.edit_text(
        "➕ <b>إضافة كروب عبر Userbot</b>\n\n"
        "أرسل أحد التالي:\n"
        "• <code>-100xxxxxxxxxx</code> (ID مباشر)\n"
        "• <code>@username</code>\n"
        "• <code>https://t.me/username</code>\n"
        "• <code>https://t.me/+inviteHash</code> (للمجموعات الخاصة)\n\n"
        "⚡ سيُستخدم حساب Userbot لجلب المعلومات.",
        reply_markup=cancel_keyboard("sessions_menu"),
        parse_mode="HTML"
    )

@router.message(SessionStates.waiting_group_id)
async def process_group_via_userbot(msg: Message, state: FSMContext):
    await state.clear()
    text = msg.text.strip()
    row  = await get_session()
    if not row:
        await msg.answer("❌ لا توجد جلسة محفوظة.")
        return

    client = _get_client(row[0])
    if client is None:
        await msg.answer("❌ Telethon غير مثبت أو API غير مضبوط.")
        return

    status_msg = await msg.answer("⏳ جاري جلب معلومات الكروب...")
    try:
        await client.connect()
        entity = await client.get_entity(text)
        group_id = entity.id
        title    = getattr(entity, "title", str(group_id))

        # تحويل ID للصيغة الصحيحة للبوتات
        if hasattr(entity, "megagroup") or hasattr(entity, "broadcast"):
            if not str(group_id).startswith("-100"):
                group_id = int(f"-100{group_id}")

        await add_group(group_id, title)
        await status_msg.edit_text(
            f"✅ <b>تم إضافة الكروب:</b>\n"
            f"📝 {title}\n"
            f"🆔 <code>{group_id}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ فشل جلب الكروب:\n<code>{e}</code>",
            parse_mode="HTML"
        )
    finally:
        await client.disconnect()
