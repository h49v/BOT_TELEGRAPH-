import os
import json
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.helpers import is_admin, back_button, parse_buttons
from database.db import get_all_replies, get_reply_by_keyword, add_reply, delete_reply, toggle_reply, is_blacklisted

router = Router()

class ReplyStates(StatesGroup):
    waiting_keyword = State()
    waiting_reply_text = State()
    waiting_reply_buttons = State()
    waiting_delete_keyword = State()

ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", 0))

# ─── Auto Reply Menu ──────────────────────────────────────
def replies_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 عرض الردود", callback_data="list_replies")],
        [InlineKeyboardButton(text="➕ إضافة رد", callback_data="add_reply")],
        [InlineKeyboardButton(text="🗑 حذف رد", callback_data="delete_reply")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")],
    ])

@router.callback_query(F.data == "autoreplies_menu")
async def cb_autoreplies_menu(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    await cb.message.edit_text("🤖 <b>الردود التلقائية:</b>", reply_markup=replies_menu_kb(), parse_mode="HTML")

# ─── List Replies ─────────────────────────────────────────
@router.callback_query(F.data == "list_replies")
async def cb_list_replies(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    replies = await get_all_replies()
    if not replies:
        await cb.message.edit_text("📭 لا توجد ردود.", reply_markup=back_button("autoreplies_menu"))
        return
    
    text = "🤖 <b>الردود التلقائية:</b>\n\n"
    buttons = []
    for r in replies:
        status = "✅" if r[4] else "⛔"
        text += f"{status} <b>{r[1]}</b> → {r[2][:40]}\n"
        buttons.append([InlineKeyboardButton(
            text=f"{'⛔ تعطيل' if r[4] else '✅ تفعيل'} | {r[1]}",
            callback_data=f"toggle_reply_{r[0]}_{0 if r[4] else 1}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="autoreplies_menu")])
    
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data.startswith("toggle_reply_"))
async def cb_toggle_reply(cb: CallbackQuery):
    parts = cb.data.split("_")
    reply_id = int(parts[2])
    active = int(parts[3])
    await toggle_reply(reply_id, active)
    await cb.answer(f"{'✅ مفعّل' if active else '⛔ معطّل'}")
    await cb_list_replies(cb)

# ─── Add Reply ────────────────────────────────────────────
@router.callback_query(F.data == "add_reply")
async def cb_add_reply(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    await state.set_state(ReplyStates.waiting_keyword)
    await cb.message.edit_text(
        "أرسل الكلمة المفتاحية للرد:",
        reply_markup=back_button("autoreplies_menu")
    )

@router.message(ReplyStates.waiting_keyword)
async def process_keyword(msg: Message, state: FSMContext):
    await state.update_data(keyword=msg.text.strip().lower())
    await state.set_state(ReplyStates.waiting_reply_text)
    await msg.answer("أرسل نص الرد:")

@router.message(ReplyStates.waiting_reply_text)
async def process_reply_text(msg: Message, state: FSMContext):
    await state.update_data(reply_text=msg.text.strip())
    await state.set_state(ReplyStates.waiting_reply_buttons)
    await msg.answer(
        "أرسل أزرار الرد (اختياري) أو أرسل <b>تخطي</b>:\n"
        "صيغة: <code>زر1|url1 , زر2|url2</code>\n"
        "أو زر callback: <code>زرنص|cb:بياناتك</code>",
        parse_mode="HTML"
    )

@router.message(ReplyStates.waiting_reply_buttons)
async def process_reply_buttons(msg: Message, state: FSMContext):
    data = await state.get_data()
    buttons_raw = None if msg.text.strip().lower() in ["تخطي", "skip"] else msg.text.strip()
    await add_reply(data["keyword"], data["reply_text"], buttons_raw)
    await state.clear()
    await msg.answer(
        f"✅ تم إضافة الرد على كلمة: <b>{data['keyword']}</b>",
        parse_mode="HTML"
    )

# ─── Delete Reply ─────────────────────────────────────────
@router.callback_query(F.data == "delete_reply")
async def cb_delete_reply_menu(cb: CallbackQuery):
    replies = await get_all_replies()
    if not replies:
        await cb.answer("لا توجد ردود!", show_alert=True)
        return
    buttons = [[InlineKeyboardButton(
        text=f"🗑 {r[1]}", callback_data=f"confirm_del_reply_{r[1]}"
    )] for r in replies]
    buttons.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="autoreplies_menu")])
    await cb.message.edit_text("اختر الرد للحذف:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("confirm_del_reply_"))
async def cb_confirm_del_reply(cb: CallbackQuery):
    keyword = cb.data[len("confirm_del_reply_"):]
    await delete_reply(keyword)
    await cb.answer(f"✅ تم حذف رد '{keyword}'")
    await cb_delete_reply_menu(cb)

# ─── Handle Incoming User Messages (Auto Reply + Forward) ─
@router.message(F.chat.type == "private")
async def handle_private_message(msg: Message, bot: Bot):
    user_id = msg.from_user.id
    
    # Skip if admin
    if await is_admin(user_id):
        return
    
    # Check blacklist
    if await is_blacklisted(user_id):
        await msg.answer("⛔ أنت محظور من استخدام هذا البوت.")
        return
    
    text = msg.text or msg.caption or ""
    
    # Check auto replies
    reply_sent = False
    replies = await get_all_replies()
    for r in replies:
        if r[4] and r[1].lower() in text.lower():  # active and keyword found
            buttons_markup = None
            if r[3]:
                buttons_markup = parse_buttons(r[3])
            await msg.answer(r[2], reply_markup=buttons_markup, parse_mode="HTML")
            reply_sent = True
            break
    
    # Forward to admin group
    if ADMIN_GROUP_ID:
        username = f"@{msg.from_user.username}" if msg.from_user.username else "بدون يوزر"
        header = (
            f"📨 <b>رسالة جديدة</b>\n"
            f"👤 {msg.from_user.full_name} | {username}\n"
            f"🆔 <code>{user_id}</code>"
        )
        view_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="👁 مشاهدة المحادثة",
                url=f"tg://user?id={user_id}"
            )
        ]])
        try:
            await bot.send_message(ADMIN_GROUP_ID, header, parse_mode="HTML", reply_markup=view_kb)
            await bot.forward_message(ADMIN_GROUP_ID, msg.chat.id, msg.message_id)
        except Exception:
            pass
