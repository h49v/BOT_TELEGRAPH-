"""
handlers/groups.py
إدارة الكروبات — إضافة عبر زر (بدون typing) + عبر Userbot
"""

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.helpers import is_admin, extract_group_id, format_group_list, back_button
from database.db import get_all_groups, add_group, remove_group, toggle_group

router = Router()

class GroupStates(StatesGroup):
    waiting_group_link = State()

# ─── Keyboards ────────────────────────────────────────────
def groups_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ إضافة كروب (يدوي)",         callback_data="add_group_manual")],
        [InlineKeyboardButton(text="🤖 إضافة كروب عبر Userbot",    callback_data="session_add_group")],
        [InlineKeyboardButton(text="📋 عرض الكروبات",              callback_data="list_groups")],
        [InlineKeyboardButton(text="🗑 حذف كروب",                  callback_data="remove_group")],
        [InlineKeyboardButton(text="🔗 استخراج ID من رابط",        callback_data="extract_id")],
        [InlineKeyboardButton(text="🔙 رجوع",                      callback_data="main_menu")],
    ])

def cancel_back(back_cb: str = "manage_groups") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 إلغاء / رجوع", callback_data=back_cb)]
    ])

# ─── Entry ────────────────────────────────────────────────
@router.callback_query(F.data == "manage_groups")
async def cb_manage_groups(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    groups = await get_all_groups()
    active = sum(1 for g in groups if g[2])
    await cb.message.edit_text(
        f"📋 <b>إدارة الكروبات</b>\n\n"
        f"📊 الإجمالي: <b>{len(groups)}</b> | نشط: <b>{active}</b>",
        reply_markup=groups_keyboard(),
        parse_mode="HTML"
    )

# ─── List Groups ──────────────────────────────────────────
@router.callback_query(F.data == "list_groups")
async def cb_list_groups(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    groups = await get_all_groups()
    text = f"📋 <b>الكروبات ({len(groups)}):</b>\n\n" + format_group_list(groups)

    buttons = []
    for g in groups:
        status_label = "⛔ تعطيل" if g[2] else "✅ تفعيل"
        buttons.append([InlineKeyboardButton(
            text=f"{status_label} | {g[1][:22]}",
            callback_data=f"toggle_group_{g[0]}_{0 if g[2] else 1}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="manage_groups")])

    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("toggle_group_"))
async def cb_toggle_group(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    # FIX: rsplit من اليمين لتجنب كسر group_id السالب
    rest     = cb.data[len("toggle_group_"):]   # "-1001234567890_1"
    group_id = int(rest.rsplit("_", 1)[0])
    active   = int(rest.rsplit("_", 1)[1])
    await toggle_group(group_id, active)
    status = "✅ مفعّل" if active else "⛔ معطّل"
    await cb.answer(f"تم تغيير الحالة → {status}")

    groups = await get_all_groups()
    text = f"📋 <b>الكروبات ({len(groups)}):</b>\n\n" + format_group_list(groups)
    buttons = []
    for g in groups:
        st = "⛔ تعطيل" if g[2] else "✅ تفعيل"
        buttons.append([InlineKeyboardButton(
            text=f"{st} | {g[1][:22]}",
            callback_data=f"toggle_group_{g[0]}_{0 if g[2] else 1}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="manage_groups")])
    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )

# ─── Add Group (Manual / Bot API) ────────────────────────
@router.callback_query(F.data == "add_group_manual")
async def cb_add_group_manual(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    await state.set_state(GroupStates.waiting_group_link)
    await cb.message.edit_text(
        "📨 <b>إضافة كروب يدوياً</b>\n\n"
        "أرسل أحد التالي:\n"
        "• <code>-100xxxxxxxxxx</code> (ID مباشر)\n"
        "• <code>@username</code>\n"
        "• <code>https://t.me/username</code>\n\n"
        "⚠️ يجب أن يكون البوت عضواً في الكروب.",
        reply_markup=cancel_back("manage_groups"),
        parse_mode="HTML"
    )

@router.message(GroupStates.waiting_group_link)
async def process_add_group(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    group_id, title = await extract_group_id(bot, msg.text.strip())
    if group_id is None:
        await msg.answer(
            f"{title}\n\nحاول مجدداً أو ارجع للقائمة.",
            reply_markup=back_button("manage_groups"),
            parse_mode="HTML"
        )
        return
    await add_group(group_id, title)
    await msg.answer(
        f"✅ <b>تم إضافة الكروب:</b>\n"
        f"📝 {title}\n"
        f"🆔 <code>{group_id}</code>",
        reply_markup=back_button("manage_groups"),
        parse_mode="HTML"
    )

# ─── Extract ID from Link ─────────────────────────────────
@router.callback_query(F.data == "extract_id")
async def cb_extract_id(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    await state.set_state(GroupStates.waiting_group_link)
    await cb.message.edit_text(
        "🔗 <b>استخراج ID من رابط</b>\n\n"
        "أرسل رابط الكروب أو القناة:\n"
        "• <code>https://t.me/username</code>\n"
        "• <code>@username</code>\n"
        "• <code>-100xxxxxxxxxx</code>\n\n"
        "⚠️ البوت يجب أن يكون عضواً في الكروب.",
        reply_markup=cancel_back("manage_groups"),
        parse_mode="HTML"
    )

# ─── Remove Group ─────────────────────────────────────────
@router.callback_query(F.data == "remove_group")
async def cb_remove_group(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    groups = await get_all_groups()
    if not groups:
        await cb.answer("📭 لا توجد كروبات مضافة.", show_alert=True)
        return
    buttons = []
    for g in groups:
        buttons.append([InlineKeyboardButton(
            text=f"🗑 {g[1][:30]}",
            callback_data=f"confirm_remove_{g[0]}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="manage_groups")])
    await cb.message.edit_text(
        "🗑 <b>اختر الكروب لحذفه:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("confirm_remove_"))
async def cb_confirm_remove(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    group_id = int(cb.data[len("confirm_remove_"):])
    await remove_group(group_id)
    await cb.answer("✅ تم الحذف")

    groups = await get_all_groups()
    if not groups:
        await cb.message.edit_text(
            "✅ تم الحذف. لا توجد كروبات متبقية.",
            reply_markup=back_button("manage_groups")
        )
        return
    buttons = []
    for g in groups:
        buttons.append([InlineKeyboardButton(
            text=f"🗑 {g[1][:30]}",
            callback_data=f"confirm_remove_{g[0]}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="manage_groups")])
    await cb.message.edit_text(
        "🗑 <b>اختر الكروب لحذفه:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
        )
