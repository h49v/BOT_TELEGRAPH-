"""
handlers/sessions.py
الحل: نبقي الـ client متصل بين send_code و sign_in
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

# ─── نحتفظ بالـ client حياً بين الخطوات ──────────────────
ACTIVE_CLIENTS = {}  # user_id → TelegramClient

class SessionStates(StatesGroup):
    waiting_phone    = State()
    waiting_code     = State()
    waiting_password = State()
    waiting_group_id = State()

def _get_api():
    api_id   = os.environ.get("API_ID", "").strip()
    api_hash = os.environ.get("API_HASH", "").strip()
    if not api_id or not api_hash:
        return None, None, "❌ API_ID أو API_HASH غير مضبوطين."
    try:
        return int(api_id), api_hash, None
    except ValueError:
        return None, None, "❌ API_ID يجب أن يكون رقماً."

async def _close_client(user_id: int):
    client = ACTIVE_CLIENTS.pop(user_id, None)
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass

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
    api_id, api_hash, err = _get_api()
    if err:
        await cb.answer(err, show_alert=True)
        return
    # أغلق أي client قديم
    await _close_client(cb.from_user.id)
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
        await msg.answer(
            "❌ صيغة خاطئة. مثال: <code>+9665xxxxxxxx</code>",
            reply_markup=cancel_kb(), parse_mode="HTML"
        )
        return

    api_id, api_hash, err = _get_api()
    if err:
        await msg.answer(err)
        await state.clear()
        return

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        await msg.answer("❌ مكتبة Telethon غير مثبتة.")
        await state.clear()
        return

    st = await msg.answer("⏳ جاري إرسال كود التحقق...")
    try:
        # ننشئ client ونبقيه متصلاً
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        result = await client.send_code_request(phone)

        # نحفظ الـ client في الذاكرة — لا نقطع الاتصال
        ACTIVE_CLIENTS[msg.from_user.id] = client

        await state.update_data(
            phone=phone,
            phone_code_hash=result.phone_code_hash
        )
        await state.set_state(SessionStates.waiting_code)
        await st.edit_text(
            "✅ <b>تم إرسال الكود على تيليجرام.</b>\n\n"
            "⚡ أرسل الكود فوراً (صالح دقيقتين فقط):",
            reply_markup=cancel_kb(),
            parse_mode="HTML"
        )
    except Exception as e:
        await _close_client(msg.from_user.id)
        await st.edit_text(f"❌ خطأ: <code>{e}</code>", parse_mode="HTML")
        await state.clear()

@router.message(SessionStates.waiting_code)
async def process_code(msg: Message, state: FSMContext):
    code = msg.text.strip().replace(" ", "")
    data = await state.get_data()
    user_id = msg.from_user.id

    client = ACTIVE_CLIENTS.get(user_id)
    if not client:
        await msg.answer(
            "❌ انتهت الجلسة، ابدأ من جديد.",
            reply_markup=cancel_kb()
        )
        await state.clear()
        return

    st = await msg.answer("⏳ جاري التحقق...")
    try:
        await client.sign_in(
            phone=data["phone"],
            code=code,
            phone_code_hash=data["phone_code_hash"]
        )
        final_session = client.session.save()
        await _close_client(user_id)
        await save_session(final_session)
        await state.clear()
        await st.edit_text(
            "✅ <b>تم تسجيل الدخول بنجاح!</b>\nالجلسة محفوظة.",
            reply_markup=sessions_keyboard(True),
            parse_mode="HTML"
        )
    except Exception as e:
        err_str = str(e)
        if "password" in err_str.lower() or "two-steps" in err_str.lower():
            await state.set_state(SessionStates.waiting_password)
            await st.edit_text(
                "🔐 حسابك محمي بكلمة مرور ثنائية.\nأرسل كلمة المرور:",
                reply_markup=cancel_kb()
            )
        else:
            await _close_client(user_id)
            await st.edit_text(f"❌ فشل: <code>{e}</code>", parse_mode="HTML")
            await state.clear()

@router.message(SessionStates.waiting_password)
async def process_password(msg: Message, state: FSMContext):
    password = msg.text.strip()
    user_id  = msg.from_user.id
    try:
        await msg.delete()
    except Exception:
        pass

    client = ACTIVE_CLIENTS.get(user_id)
    if not client:
        await msg.answer("❌ انتهت الجلسة، ابدأ من جديد.")
        await state.clear()
        return

    st = await msg.answer("⏳ جاري التحقق...")
    try:
        await client.sign_in(password=password)
        final_session = client.session.save()
        await _close_client(user_id)
        await save_session(final_session)
        await state.clear()
        await st.edit_text(
            "✅ <b>تم تسجيل الدخول بنجاح!</b>",
            reply_markup=sessions_keyboard(True),
            parse_mode="HTML"
        )
    except Exception as e:
        await _close_client(user_id)
        await st.edit_text(f"❌ كلمة المرور خاطئة: <code>{e}</code>", parse_mode="HTML")
        await state.clear()

@router.callback_query(F.data == "session_add_group")
async def cb_session_add_group(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    row = await get_session()
    if not row:
        await cb.answer("❌ لا توجد جلسة. استخرج جلسة أولاً.", show_alert=True)
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

    api_id, api_hash, err = _get_api()
    if err:
        await msg.answer(err)
        return

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        await msg.answer("❌ مكتبة Telethon غير مثبتة.")
        return

    st = await msg.answer("⏳ جاري جلب معلومات الكروب...")
    client = None
    try:
        client = TelegramClient(StringSession(row[0]), api_id, api_hash)
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
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass
