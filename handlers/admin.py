from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.helpers import is_admin, is_main_admin, main_menu_keyboard, back_button
from database.db import get_all_admins, add_admin, remove_admin, get_all_features, set_feature

router = Router()

FEATURE_LABELS = {
    "broadcast":    "📢 البث للكروبات",
    "templates":    "🧩 القوالب",
    "auto_reply":   "🤖 الردود التلقائية",
    "groups_view":  "📋 عرض الكروبات",
    "stats_view":   "📊 الإحصائيات",
}

class AdminStates(StatesGroup):
    waiting_add_admin    = State()
    waiting_remove_admin = State()

# ─── /start ───────────────────────────────────────────────
@router.message(Command("start"))
async def cmd_start(msg: Message):
    is_adm  = await is_admin(msg.from_user.id)
    is_main = await is_main_admin(msg.from_user.id)

    if is_adm:
        await msg.answer(
            "👋 أهلاً في <b>CyberBand Bot</b>\nاختر من القائمة:",
            reply_markup=main_menu_keyboard(is_main),
            parse_mode="HTML"
        )
    else:
        # مستخدم عادي — يشوف فقط الوظائف المفعّلة
        features = await get_all_features()
        buttons  = []
        if features.get("broadcast"):
            buttons.append([InlineKeyboardButton(text="📢 إرسال للكروبات", callback_data="pub_broadcast")])
        if features.get("templates"):
            buttons.append([InlineKeyboardButton(text="🧩 القوالب",         callback_data="pub_templates")])
        if features.get("auto_reply"):
            buttons.append([InlineKeyboardButton(text="🤖 الردود التلقائية", callback_data="pub_autoreplies")])
        if features.get("groups_view"):
            buttons.append([InlineKeyboardButton(text="📋 الكروبات",         callback_data="pub_groups")])
        if features.get("stats_view"):
            buttons.append([InlineKeyboardButton(text="📊 الإحصائيات",       callback_data="pub_stats")])

        if not buttons:
            await msg.answer("👋 أهلاً!\n\n⛔ لا توجد خدمات متاحة حالياً.")
            return

        await msg.answer(
            "👋 أهلاً! اختر الخدمة:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )

# ─── Main Menu Callback ───────────────────────────────────
@router.callback_query(F.data == "main_menu")
async def cb_main_menu(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return
    is_main = await is_main_admin(cb.from_user.id)
    await cb.message.edit_text(
        "👋 القائمة الرئيسية:",
        reply_markup=main_menu_keyboard(is_main),
        parse_mode="HTML"
    )

# ─── Admins Menu ──────────────────────────────────────────
@router.callback_query(F.data == "admins_menu")
async def cb_admins_menu(cb: CallbackQuery):
    if not await is_main_admin(cb.from_user.id):
        await cb.answer("⛔ للمشرف الرئيسي فقط.", show_alert=True)
        return
    admins = await get_all_admins()
    text   = "👥 <b>المشرفون:</b>\n\n"
    for a in admins:
        role  = "👑 رئيسي" if a[2] == "main" else "🔧 فرعي"
        text += f"• {role} | <code>{a[0]}</code> @{a[1] or 'N/A'}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ إضافة مشرف",      callback_data="add_admin")],
        [InlineKeyboardButton(text="➖ حذف مشرف",        callback_data="remove_admin")],
        [InlineKeyboardButton(text="⚙️ إعدادات العموم",  callback_data="features_menu")],
        [InlineKeyboardButton(text="🔙 رجوع",            callback_data="main_menu")],
    ])
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

# ─── Feature Flags Menu ───────────────────────────────────
@router.callback_query(F.data == "features_menu")
async def cb_features_menu(cb: CallbackQuery):
    if not await is_main_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    features = await get_all_features()
    buttons  = []
    for key, label in FEATURE_LABELS.items():
        status = "✅ مفتوح" if features.get(key) else "🔒 مغلق"
        buttons.append([InlineKeyboardButton(
            text=f"{status} | {label}",
            callback_data=f"toggle_feature_{key}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="admins_menu")])
    await cb.message.edit_text(
        "⚙️ <b>التحكم بالوظائف المتاحة للعموم:</b>\n\n"
        "اضغط على الوظيفة لتفعيلها أو إغلاقها:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("toggle_feature_"))
async def cb_toggle_feature(cb: CallbackQuery):
    if not await is_main_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    feature  = cb.data[len("toggle_feature_"):]
    features = await get_all_features()
    current  = features.get(feature, False)
    await set_feature(feature, not current)
    label    = FEATURE_LABELS.get(feature, feature)
    status   = "✅ مفتوح للعموم" if not current else "🔒 مغلق"
    await cb.answer(f"{label}\n{status}", show_alert=True)
    # أعد رسم القائمة
    await cb_features_menu(cb)

# ─── Public callbacks (للمستخدمين العاديين) ──────────────
@router.callback_query(F.data == "pub_broadcast")
async def cb_pub_broadcast(cb: CallbackQuery, state: FSMContext):
    from database.db import is_feature_enabled, is_blacklisted
    if await is_blacklisted(cb.from_user.id):
        await cb.answer("⛔ أنت محظور.", show_alert=True)
        return
    if not await is_feature_enabled("broadcast"):
        await cb.answer("⛔ هذه الخدمة غير متاحة حالياً.", show_alert=True)
        return
    # أعد توجيه لنفس handler البث
    from aiogram.types import CallbackQuery as CQ
    cb.data = "new_broadcast"
    from handlers.broadcast import cb_new_broadcast
    await cb_new_broadcast(cb, state)

@router.callback_query(F.data == "pub_templates")
async def cb_pub_templates(cb: CallbackQuery):
    from database.db import is_feature_enabled, is_blacklisted
    if await is_blacklisted(cb.from_user.id):
        await cb.answer("⛔ أنت محظور.", show_alert=True)
        return
    if not await is_feature_enabled("templates"):
        await cb.answer("⛔ هذه الخدمة غير متاحة حالياً.", show_alert=True)
        return
    cb.data = "templates_menu"
    from handlers.broadcast import cb_templates_menu
    await cb_templates_menu(cb)

@router.callback_query(F.data == "pub_autoreplies")
async def cb_pub_autoreplies(cb: CallbackQuery):
    from database.db import is_feature_enabled, is_blacklisted
    if await is_blacklisted(cb.from_user.id):
        await cb.answer("⛔ أنت محظور.", show_alert=True)
        return
    if not await is_feature_enabled("auto_reply"):
        await cb.answer("⛔ هذه الخدمة غير متاحة حالياً.", show_alert=True)
        return
    cb.data = "autoreplies_menu"
    from handlers.auto_reply import cb_autoreplies_menu
    await cb_autoreplies_menu(cb)

@router.callback_query(F.data == "pub_groups")
async def cb_pub_groups(cb: CallbackQuery):
    from database.db import is_feature_enabled, is_blacklisted
    if await is_blacklisted(cb.from_user.id):
        await cb.answer("⛔ أنت محظور.", show_alert=True)
        return
    if not await is_feature_enabled("groups_view"):
        await cb.answer("⛔ هذه الخدمة غير متاحة حالياً.", show_alert=True)
        return
    cb.data = "list_groups"
    from handlers.groups import cb_list_groups
    await cb_list_groups(cb)

@router.callback_query(F.data == "pub_stats")
async def cb_pub_stats(cb: CallbackQuery):
    from database.db import is_feature_enabled, is_blacklisted
    if await is_blacklisted(cb.from_user.id):
        await cb.answer("⛔ أنت محظور.", show_alert=True)
        return
    if not await is_feature_enabled("stats_view"):
        await cb.answer("⛔ هذه الخدمة غير متاحة حالياً.", show_alert=True)
        return
    cb.data = "stats_menu"
    from handlers.stats import cb_stats
    await cb_stats(cb)

# ─── Add / Remove Admin ───────────────────────────────────
@router.callback_query(F.data == "add_admin")
async def cb_add_admin(cb: CallbackQuery, state: FSMContext):
    if not await is_main_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_add_admin)
    await cb.message.edit_text("أرسل ID المستخدم الجديد:", reply_markup=back_button("admins_menu"))

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
    await cb.message.edit_text("أرسل ID المشرف لحذفه:", reply_markup=back_button("admins_menu"))

@router.message(AdminStates.waiting_remove_admin)
async def process_remove_admin(msg: Message, state: FSMContext):
    await state.clear()
    try:
        uid = int(msg.text.strip())
        await remove_admin(uid)
        await msg.answer(f"✅ تم حذف المشرف <code>{uid}</code>", parse_mode="HTML")
    except ValueError:
        await msg.answer("❌ ID غير صحيح.")

# ─── /id command ──────────────────────────────────────────
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
