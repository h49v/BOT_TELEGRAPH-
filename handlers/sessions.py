"""
handlers/sessions.py
إدارة جلسات Telethon (Userbot)
"""

import os
import re
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.helpers import is_admin, is_main_admin, back_button
from database.db import save_session, get_session, delete_session, add_group

logger = logging.getLogger(__name__)
router = Router()

class SessionStates(StatesGroup):
    waiting_phone    = State()
    waiting_code     = State()
    waiting_password = State()
    waiting_group_id = State()

def _make_client(session_string: str = None):
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        return None, "❌ مكتبة Telethon غير مثبتة."

    api_id   = os.environ.get("API_ID", "").strip()
    api_hash = os.environ.get("API_HASH", "").strip()

    if not api_id or not api_hash:
        return None, "❌ API_ID أو API_HASH غير مضبوطين."

    try:
        api_id = int(api_id)
    except ValueError:
        return None, "❌ API_ID يجب أن يكون رقماً."

    from telethon.sessions import StringSession
    from telethon import TelegramClient
    return TelegramClient(StringSession(session_string or ""), api_id, api_hash), None

def sessions_keyboard(has_session: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_session:
        rows += [
            [InlineKeyboardButton(text="📋 عرض الجلسة",             callback_data="session_view")],
            [InlineKeyboardButton(text="➕ إضافة كروب عبر Userbot", callback_data="session_add_group")],
            [InlineKeyboardButton(text="🔄 تحديث الجلسة",           callback_data="session_new")],
            [InlineKeyboardButton(text="🗑 حذف الجلسة",             callback_data="session_delete")],
        ]
    else:
        rows += [
            [InlineKeyboardButton(text="🔑 استخراج جلسة جديدة",    callback_data="session_new")],
        ]
    rows.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def cancel_kb(back_cb: str = "sessions_menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ إلغاء", callback_data=back_cb)]
    ])

@router.callback_query(F.data == "sessions_menu")
async def cb_sessions_menu(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    row = await get_session()
    has = row is not None
    status = "✅ جلسة نشطة" if has else "❌ لا توجد جلسة"
    await cb.message.edit_text(
        f"📱 <b>إدارة جلسة Userbot</b>\n\nالحالة: {status}",
        reply_markup=sessions_keyboard(has),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "session_view")
async def cb_session_view(cb: CallbackQuery):
    if not await is_main_admin(cb.from_user.id):
        await cb.answer("⛔ للمشرف الرئيسي فقط.", show_alert=True)
        return
    row = await get_session()
    if not row:
        await cb.answer("لا توجد جلسة.", show_alert=True)
        return
    s = row[0]
    preview = f"{s[:10]}...{s[-10:]}" if len(s) > 25 else s
    await cb.message.edit_text(
        f"📋 <b>الجلسة الحالية:</b>\n<code>{preview}</code>",
        reply_markup=back_button("sessions_menu"),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "session_delete")
async def cb_session_delete(cb: CallbackQuery):
    if not await is_main_admin(cb.from_user.id):
        await cb.answer("⛔ للمشرف الرئيسي فقط.", show_alert=True)
        return
    await delete_session()
    await cb.answer("✅ تم الحذف.", show_alert=True)
    await cb.message.edit_text(
        "📱 <b>إدارة جلسة Userbot</b>\n\nالحالة: ❌ لا توجد جلسة",
        reply_markup=sessions_keyboard(False),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "session_new")
async def cb_session_new(cb: CallbackQuery, state: FSMContext):
    if not await is_main_admin(cb.from_user.id):
        await cb.answer("⛔ للمشرف الرئيسي فقط.", show_alert=True)
        return
    client, err = _make_client()
    if client is None:
        await cb.answer(err, show_alert=True)
        return
    await state.set_state(SessionStates.waiting_phone)
    await cb.message.edit_text(
        "📱 <b>استخراج جلسة Telethon</b>\n\n"
        "أرسل رقم هاتفك:\n<code>+9665xxxxxxxx</code>",
        reply_markup=cancel_kb("sessions_menu"),
        parse_mode="HTML"
    )

@router.message(SessionStates.waiting_phone)
async def process_phone(msg: Message, state: FSMContext):
    phone = msg.text.strip()
    if not re.match(r"^\+\d{7,15}$", phone):
        await msg.answer("❌ صيغة خاطئة. مثال: <code>+9665xxxxxxxx</code>",
                         reply_markup=cancel_kb(), parse_mode="HTML")
        return
    client, err = _make_client()
    if client is None:
        await msg.answer(err)
        await state.clear()
        return
    st = await msg.answer("⏳ جاري الاتصال...")
    try:
        await client.connect()
        result = await client.send_code_request(phone)
        await state.update_data(phone=phone,
                                phone_code_hash=result.phone_code_hash,
                                session_str=client.session.save())
        await state.set_state(SessionStates.waiting_code)
        await st.edit_text("✅ تم إرسال الكود.\n\nأرسل الكود (5 أرقام):",
                           reply_markup=cancel_kb())
    except Exception as e:
        await st.edit_text(f"❌ خطأ: <code>{e}</code>", parse_mode="HTML")
        await state.clear()
    finally:
        await client.disconnect()

@router.message(SessionStates.waiting_code)
async def process_code(msg: Message, state: FSMContext):
    code = msg.text.strip().replace(" ", "")
    data = await state.get_data()
    client, err = _make_client(data.get("session_str"))
    if client is None:
        await msg.answer(err)
        await state.clear()
        return
    st = await msg.answer("⏳ جاري التحقق...")
    try:
        await client.connect()
        await client.sign_in(data["phone"], code, phone_code_hash=data["phone_code_hash"])
        await save_session(client.session.save())
        await state.clear()
        await st.edit_text("✅ <b>تم تسجيل الدخول!</b>",
                           reply_markup=sessions_keyboard(True), parse_mode="HTML")
    except Exception as e:
        if "password" in str(e).lower() or "two" in str(e).lower():
            await state.update_data(session_str=client.session.save())
            await state.set_state(SessionStates.waiting_password)
            await st.edit_text("🔐 أرسل كلمة مرور التحقق الثنائي:",
                               reply_markup=cancel_kb())
        else:
            await st.edit_text(f"❌ فشل: <code>{e}</code>", parse_mode="HTML")
            await state.clear()
    finally:
        await client.disconnect()

@router.message(SessionStates.waiting_password)
async def process_password(msg: Message, state: FSMContext):
    password = msg.text.strip()
    data = await state.get_data()
    try:
        await msg.delete()
    except Exception:
        pass
    client, err = _make_client(data.get("session_str"))
    if client is None:
        await msg.answer(err)
        await state.clear()
        return
    st = await msg.answer("⏳ جاري التحقق...")
    try:
        await client.connect()
        await client.sign_in(password=password)
        await save_session(client.session.save())
        await state.clear()
        await st.edit_text("✅ <b>تم تسجيل الدخول!</b>",
                           reply_markup=sessions_keyboard(True), parse_mode="HTML")
    except Exception as e:
        await st.edit_text(f"❌ كلمة المرور خاطئة: <code>{e}</code>", parse_mode="HTML")
        await state.clear()
    finally:
        await client.disconnect()

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
        "• <code>-100xxxxxxxxxx</code>\n"
        "• <code>@username</code>\n"
        "• <code>https://t.me/username</code>\n"
        "• <code>https://t.me/+inviteHash</code>",
        reply_markup=cancel_kb("sessions_menu"),
        parse_mode="HTML"
    )

@router.message(SessionStates.waiting_group_id)
async def process_group_userbot(msg: Message, state: FSMContext):
    await state.clear()
    text = msg.text.strip()
    row  = await get_session()
    if not row:
        await msg.answer("❌ لا توجد جلسة.")
        return
    client, err = _make_client(row[0])
    if client is None:
        await msg.answer(err)
        return
    st = await msg.answer("⏳ جاري جلب معلومات الكروب...")
    try:
        await client.connect()
        entity   = await client.get_entity(text)
        group_id = entity.id
        title    = getattr(entity, "title", str(group_id))
        if not str(group_id).startswith("-100"):
            group_id = int(f"-100{group_id}")
        await add_group(group_id, title)
        await st.edit_text(
            f"✅ <b>تم إضافة:</b>\n📝 {title}\n🆔 <code>{group_id}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        await st.edit_text(f"❌ فشل: <code>{e}</code>", parse_mode="HTML")
    finally:
        await client.disconnect()
