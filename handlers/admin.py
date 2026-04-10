from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.helpers import is_admin, is_main_admin, main_menu_keyboard, back_button
from database.db import get_all_admins, add_admin, remove_admin

router = Router()

class AdminStates(StatesGroup):
    waiting_add_admin = State()
    waiting_remove_admin = State()

# ─── /start ───────────────────────────────────────────────
@router.message(Command("start"))
async def cmd_start(msg: Message):
    if not await is_admin(msg.from_user.id):
        await msg.answer("⛔ ليس لديك صلاحية.")
        return
    main = await is_main_admin(msg.from_user.id)
    await msg.answer(
        "👋 أهلاً في <b>CyberBand Bot</b>\nاختر من القائمة:",
        reply_markup=main_menu_keyboard(main),
        parse_mode="HTML"
    )

# ─── Main Menu Callback ───────────────────────────────────
@router.callback_query(F.data == "main_menu")
async def cb_main_menu(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return
    main = await is_main_admin(cb.from_user.id)
    await cb.message.edit_text(
        "👋 القائمة الرئيسية:",
        reply_markup=main_menu_keyboard(main),
        parse_mode="HTML"
    )

# ─── Admins Menu ──────────────────────────────────────────
@router.callback_query(F.data == "admins_menu")
async def cb_admins_menu(cb: CallbackQuery):
    if not await is_main_admin(cb.from_user.id):
        await cb.answer("⛔ للمشرف الرئيسي فقط.", show_alert=True)
        return
    admins = await get_all_admins()
    text = "👥 <b>المشرفون:</b>\n\n"
    for a in admins:
        role = "👑 رئيسي" if a[2] == "main" else "🔧 فرعي"
        text += f"• {role} | <code>{a[0]}</code> @{a[1] or 'N/A'}\n"
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ إضافة مشرف", callback_data="add_admin")],
        [InlineKeyboardButton(text="➖ حذف مشرف", callback_data="remove_admin")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")],
    ])
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "add_admin")
async def cb_add_admin(cb: CallbackQuery, state: FSMContext):
    if not await is_main_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_add_admin)
    await cb.message.edit_text(
        "أرسل ID المستخدم الجديد:",
        reply_markup=back_button("admins_menu")
    )

@router.message(AdminStates.waiting_add_admin)
async def process_add_admin(msg: Message, state: FSMContext):
    await state.clear()
    try:
        uid = int(msg.text.strip())
        await add_admin(uid, None, "sub")
        await msg.answer(f"✅ تم إضافة المشرف <code>{uid}</code>", parse_mode="HTML")
    except ValueError:
        await msg.answer("❌ ID غير صحيح.")

@router.callback_query(F.data == "remove_admin")
async def cb_remove_admin(cb: CallbackQuery, state: FSMContext):
    if not await is_main_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_remove_admin)
    await cb.message.edit_text(
        "أرسل ID المشرف لحذفه:",
        reply_markup=back_button("admins_menu")
    )

@router.message(AdminStates.waiting_remove_admin)
async def process_remove_admin(msg: Message, state: FSMContext):
    await state.clear()
    try:
        uid = int(msg.text.strip())
        await remove_admin(uid)
        await msg.answer(f"✅ تم حذف المشرف <code>{uid}</code>", parse_mode="HTML")
    except ValueError:
        await msg.answer("❌ ID غير صحيح.")

# ─── /id command (get group ID) ───────────────────────────
@router.message(Command("id"))
async def cmd_get_id(msg: Message):
    chat = msg.chat
    await msg.answer(
        f"🆔 <b>معلومات المحادثة:</b>\n"
        f"• الاسم: <b>{chat.title or chat.full_name}</b>\n"
        f"• ID: <code>{chat.id}</code>\n"
        f"• النوع: {chat.type}",
        parse_mode="HTML"
    )
