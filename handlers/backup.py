import json
import io
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.helpers import is_admin, is_main_admin, back_button
from database.db import (
    get_blacklist, add_blacklist, remove_blacklist,
    get_all_groups, get_all_templates, get_all_replies, get_scheduled
)

router = Router()

class BlacklistStates(StatesGroup):
    waiting_ban_id = State()
    waiting_ban_reason = State()
    waiting_unban_id = State()

# ─── Blacklist Menu ───────────────────────────────────────
def blacklist_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 عرض المحظورين", callback_data="list_blacklist")],
        [InlineKeyboardButton(text="🚫 حظر مستخدم", callback_data="ban_user")],
        [InlineKeyboardButton(text="✅ رفع الحظر", callback_data="unban_user")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")],
    ])

@router.callback_query(F.data == "blacklist_menu")
async def cb_blacklist_menu(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    await cb.message.edit_text("🚫 <b>القائمة السوداء:</b>", reply_markup=blacklist_kb(), parse_mode="HTML")

@router.callback_query(F.data == "list_blacklist")
async def cb_list_blacklist(cb: CallbackQuery):
    bl = await get_blacklist()
    if not bl:
        await cb.message.edit_text("✅ لا يوجد محظورون.", reply_markup=back_button("blacklist_menu"))
        return
    text = "🚫 <b>المحظورون:</b>\n\n"
    for u in bl:
        text += f"• <code>{u[0]}</code> | {u[1] or 'بدون سبب'}\n  📅 {u[2]}\n"
    await cb.message.edit_text(text, reply_markup=back_button("blacklist_menu"), parse_mode="HTML")

@router.callback_query(F.data == "ban_user")
async def cb_ban_user(cb: CallbackQuery, state: FSMContext):
    if not await is_main_admin(cb.from_user.id):
        await cb.answer("⛔ للمشرف الرئيسي فقط.", show_alert=True)
        return
    await state.set_state(BlacklistStates.waiting_ban_id)
    await cb.message.edit_text("أرسل ID المستخدم لحظره:", reply_markup=back_button("blacklist_menu"))

@router.message(BlacklistStates.waiting_ban_id)
async def process_ban_id(msg: Message, state: FSMContext):
    try:
        uid = int(msg.text.strip())
        await state.update_data(ban_id=uid)
        await state.set_state(BlacklistStates.waiting_ban_reason)
        await msg.answer("أرسل سبب الحظر (أو أرسل <b>تخطي</b>):", parse_mode="HTML")
    except ValueError:
        await msg.answer("❌ ID غير صحيح.")
        await state.clear()

@router.message(BlacklistStates.waiting_ban_reason)
async def process_ban_reason(msg: Message, state: FSMContext):
    data = await state.get_data()
    reason = "" if msg.text.strip().lower() in ["تخطي", "skip"] else msg.text.strip()
    await add_blacklist(data["ban_id"], reason)
    await state.clear()
    await msg.answer(f"✅ تم حظر <code>{data['ban_id']}</code>", parse_mode="HTML")

@router.callback_query(F.data == "unban_user")
async def cb_unban_user(cb: CallbackQuery, state: FSMContext):
    if not await is_main_admin(cb.from_user.id):
        await cb.answer("⛔ للمشرف الرئيسي فقط.", show_alert=True)
        return
    await state.set_state(BlacklistStates.waiting_unban_id)
    await cb.message.edit_text("أرسل ID المستخدم لرفع الحظر:", reply_markup=back_button("blacklist_menu"))

@router.message(BlacklistStates.waiting_unban_id)
async def process_unban(msg: Message, state: FSMContext):
    await state.clear()
    try:
        uid = int(msg.text.strip())
        await remove_blacklist(uid)
        await msg.answer(f"✅ تم رفع الحظر عن <code>{uid}</code>", parse_mode="HTML")
    except ValueError:
        await msg.answer("❌ ID غير صحيح.")

# ─── Backup ───────────────────────────────────────────────
@router.callback_query(F.data == "backup_menu")
async def cb_backup_menu(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 تصدير النسخة الاحتياطية", callback_data="export_backup")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")],
    ])
    await cb.message.edit_text("💾 <b>النسخ الاحتياطي:</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "export_backup")
async def cb_export_backup(cb: CallbackQuery, bot: Bot):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    
    groups = await get_all_groups()
    templates = await get_all_templates()
    replies = await get_all_replies()
    scheduled = await get_scheduled()
    
    backup_data = {
        "groups": [{"id": g[0], "title": g[1], "active": g[2]} for g in groups],
        "templates": [{"name": t[1], "content": t[2], "media_type": t[4]} for t in templates],
        "auto_replies": [{"keyword": r[1], "reply": r[2], "buttons": r[3]} for r in replies],
        "scheduled": [{"template": s[1], "time": s[2], "interval": s[3]} for s in scheduled],
    }
    
    backup_json = json.dumps(backup_data, ensure_ascii=False, indent=2)
    file_bytes = backup_json.encode("utf-8")
    
    from datetime import datetime
    filename = f"cyberband_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    await cb.message.answer_document(
        BufferedInputFile(file_bytes, filename=filename),
        caption="✅ <b>النسخة الاحتياطية جاهزة</b>",
        parse_mode="HTML"
    )
    await cb.answer()
