import asyncio
import re
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.helpers import is_admin, is_feature_allowed, back_button, parse_buttons
from database.db import (
    get_active_groups, get_all_templates, get_template,
    add_template, delete_template, log_broadcast,
    add_scheduled, get_scheduled, remove_scheduled
)

router = Router()

class BroadcastStates(StatesGroup):
    waiting_message          = State()
    waiting_template_name    = State()
    waiting_template_content = State()
    waiting_template_buttons = State()
    waiting_schedule_time    = State()
    waiting_schedule_interval = State()

PENDING_BROADCAST = {}

# ─── Broadcast Menu ───────────────────────────────────────
def broadcast_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 إرسال رسالة جديدة",   callback_data="new_broadcast")],
        [InlineKeyboardButton(text="🧩 إرسال من قالب",       callback_data="broadcast_from_template")],
        [InlineKeyboardButton(text="📜 سجل النشر",           callback_data="broadcast_log")],
        [InlineKeyboardButton(text="🔙 رجوع",                callback_data="main_menu")],
    ])

@router.callback_query(F.data == "broadcast_menu")
async def cb_broadcast_menu(cb: CallbackQuery):
    if not await is_feature_allowed(cb.from_user.id, "broadcast"):
        await cb.answer("⛔ هذه الخدمة غير متاحة حالياً.", show_alert=True)
        return
    await cb.message.edit_text("📢 <b>قائمة النشر:</b>", reply_markup=broadcast_menu_kb(), parse_mode="HTML")

# ─── New Broadcast ────────────────────────────────────────
@router.callback_query(F.data == "new_broadcast")
async def cb_new_broadcast(cb: CallbackQuery, state: FSMContext):
    if not await is_feature_allowed(cb.from_user.id, "broadcast"):
        await cb.answer("⛔ هذه الخدمة غير متاحة حالياً.", show_alert=True)
        return
    await state.set_state(BroadcastStates.waiting_message)
    await cb.message.edit_text(
        "✍️ أرسل الرسالة (نص أو صورة أو فيديو):\n\n"
        "للأزرار أضف في السطر الأخير:\n"
        "<code>#buttons\nزر1|https://... , زر2|https://...</code>",
        reply_markup=back_button("broadcast_menu"),
        parse_mode="HTML"
    )

@router.message(BroadcastStates.waiting_message)
async def process_broadcast_message(msg: Message, state: FSMContext):
    await state.clear()
    user_id = msg.from_user.id

    buttons_markup = None
    text = msg.text or msg.caption or ""
    if "#buttons" in text:
        parts = text.split("#buttons", 1)
        clean_text = parts[0].strip()
        buttons_markup = parse_buttons(parts[1].strip())
    else:
        clean_text = text

    PENDING_BROADCAST[user_id] = {
        "text":    clean_text,
        "buttons": buttons_markup,
        "photo":   msg.photo[-1].file_id if msg.photo else None,
        "video":   msg.video.file_id if msg.video else None,
    }

    preview_text = f"👁 <b>معاينة الرسالة:</b>\n\n{clean_text}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ إرسال الآن", callback_data="confirm_broadcast")],
        [InlineKeyboardButton(text="❌ إلغاء",      callback_data="broadcast_menu")],
    ])
    await msg.answer(preview_text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "confirm_broadcast")
async def cb_confirm_broadcast(cb: CallbackQuery, bot: Bot):
    user_id = cb.from_user.id
    if user_id not in PENDING_BROADCAST:
        await cb.answer("انتهت صلاحية الرسالة.", show_alert=True)
        return

    data   = PENDING_BROADCAST.pop(user_id)
    groups = await get_active_groups()
    if not groups:
        await cb.answer("لا توجد كروبات نشطة!", show_alert=True)
        return

    await cb.message.edit_text(f"⏳ جاري الإرسال لـ {len(groups)} كروب...")
    sent, failed = await send_to_groups(bot, groups, data)
    await log_broadcast("manual", sent, failed)

    await cb.message.edit_text(
        f"✅ <b>اكتمل الإرسال</b>\n• نجح: <b>{sent}</b>\n• فشل: <b>{failed}</b>",
        reply_markup=back_button("broadcast_menu"),
        parse_mode="HTML"
    )

# ─── Send to Groups ───────────────────────────────────────
async def send_to_groups(bot: Bot, groups: list, data: dict, delay: float = 0.3) -> tuple[int, int]:
    sent = failed = 0
    for group_id, title in groups:
        try:
            kwargs = {"reply_markup": data.get("buttons")}
            if data.get("photo"):
                await bot.send_photo(group_id, data["photo"], caption=data.get("text", ""), **kwargs)
            elif data.get("video"):
                await bot.send_video(group_id, data["video"], caption=data.get("text", ""), **kwargs)
            else:
                await bot.send_message(group_id, data["text"], parse_mode="HTML", **kwargs)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(delay)
    return sent, failed

# ─── Broadcast from Template ──────────────────────────────
@router.callback_query(F.data == "broadcast_from_template")
async def cb_broadcast_from_template(cb: CallbackQuery):
    if not await is_feature_allowed(cb.from_user.id, "broadcast"):
        await cb.answer("⛔ هذه الخدمة غير متاحة حالياً.", show_alert=True)
        return
    templates = await get_all_templates()
    if not templates:
        await cb.answer("لا توجد قوالب!", show_alert=True)
        return
    buttons = [[InlineKeyboardButton(
        text=f"🧩 {t[1]}", callback_data=f"use_template_{t[1]}"
    )] for t in templates]
    buttons.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="broadcast_menu")])
    await cb.message.edit_text(
        "اختر القالب للإرسال:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@router.callback_query(F.data.startswith("use_template_"))
async def cb_use_template(cb: CallbackQuery, bot: Bot):
    name = cb.data[len("use_template_"):]
    tmpl = await get_template(name)
    if not tmpl:
        await cb.answer("القالب غير موجود!", show_alert=True)
        return

    groups = await get_active_groups()
    if not groups:
        await cb.answer("لا توجد كروبات نشطة!", show_alert=True)
        return

    await cb.message.edit_text(f"⏳ جاري إرسال قالب «{name}» لـ {len(groups)} كروب...")

    # FIX: tmpl = (id, name, content, media_path, media_type, buttons)
    buttons_markup = parse_buttons(tmpl[5]) if tmpl[5] else None
    data = {
        "text":    tmpl[2],
        "buttons": buttons_markup,
        "photo":   tmpl[3] if tmpl[4] == "photo" else None,
        "video":   tmpl[3] if tmpl[4] == "video" else None,
    }
    sent, failed = await send_to_groups(bot, groups, data)
    await log_broadcast(name, sent, failed)

    await cb.message.edit_text(
        f"✅ <b>اكتمل الإرسال</b>\n• نجح: <b>{sent}</b>\n• فشل: <b>{failed}</b>",
        reply_markup=back_button("broadcast_menu"),
        parse_mode="HTML"
    )

# ─── Broadcast Log ────────────────────────────────────────
@router.callback_query(F.data == "broadcast_log")
async def cb_broadcast_log(cb: CallbackQuery):
    from database.db import get_broadcast_logs
    logs = await get_broadcast_logs(20)
    if not logs:
        await cb.message.edit_text("📭 لا يوجد سجل.", reply_markup=back_button("broadcast_menu"))
        return
    text = "📜 <b>سجل النشر (آخر 20):</b>\n\n"
    for log in logs:
        text += f"• <b>{log[0]}</b> ✅{log[1]} ❌{log[2]}\n  🕐 {log[3]}\n\n"
    await cb.message.edit_text(text, reply_markup=back_button("broadcast_menu"), parse_mode="HTML")

# ─── Templates Menu ───────────────────────────────────────
def templates_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 عرض القوالب", callback_data="list_templates")],
        [InlineKeyboardButton(text="➕ إضافة قالب",  callback_data="add_template")],
        [InlineKeyboardButton(text="🗑 حذف قالب",    callback_data="delete_template")],
        [InlineKeyboardButton(text="🔙 رجوع",        callback_data="main_menu")],
    ])

@router.callback_query(F.data == "templates_menu")
async def cb_templates_menu(cb: CallbackQuery):
    if not await is_feature_allowed(cb.from_user.id, "templates"):
        await cb.answer("⛔ هذه الخدمة غير متاحة حالياً.", show_alert=True)
        return
    await cb.message.edit_text("🧩 <b>القوالب:</b>", reply_markup=templates_menu_kb(), parse_mode="HTML")

@router.callback_query(F.data == "list_templates")
async def cb_list_templates(cb: CallbackQuery):
    templates = await get_all_templates()
    if not templates:
        await cb.message.edit_text("📭 لا توجد قوالب.", reply_markup=back_button("templates_menu"))
        return
    text = "🧩 <b>القوالب:</b>\n\n"
    for t in templates:
        media = f"📎 {t[3]}" if t[3] else ""
        text += f"• <b>{t[1]}</b> {media}\n  {t[2][:50]}...\n\n"
    await cb.message.edit_text(text, reply_markup=back_button("templates_menu"), parse_mode="HTML")

@router.callback_query(F.data == "add_template")
async def cb_add_template(cb: CallbackQuery, state: FSMContext):
    if not await is_feature_allowed(cb.from_user.id, "templates"):
        await cb.answer("⛔ هذه الخدمة غير متاحة حالياً.", show_alert=True)
        return
    await state.set_state(BroadcastStates.waiting_template_name)
    await cb.message.edit_text(
        "أرسل اسم القالب (بدون مسافات):",
        reply_markup=back_button("templates_menu")
    )

@router.message(BroadcastStates.waiting_template_name)
async def process_template_name(msg: Message, state: FSMContext):
    await state.update_data(template_name=msg.text.strip())
    await state.set_state(BroadcastStates.waiting_template_content)
    await msg.answer("أرسل محتوى القالب (نص أو صورة مع كابشن):")

@router.message(BroadcastStates.waiting_template_content)
async def process_template_content(msg: Message, state: FSMContext):
    content    = msg.text or msg.caption or ""
    media_path = None
    media_type = None
    if msg.photo:
        media_path = msg.photo[-1].file_id
        media_type = "photo"
    elif msg.video:
        media_path = msg.video.file_id
        media_type = "video"

    await state.update_data(content=content, media_path=media_path, media_type=media_type)
    await state.set_state(BroadcastStates.waiting_template_buttons)
    await msg.answer(
        "أرسل أزرار القالب (اختياري) أو أرسل <b>تخطي</b>:\n"
        "صيغة: <code>زر1|url1 , زر2|url2</code>",
        parse_mode="HTML"
    )

@router.message(BroadcastStates.waiting_template_buttons)
async def process_template_buttons(msg: Message, state: FSMContext):
    data = await state.get_data()
    # FIX: حفظ الأزرار فعلياً في قاعدة البيانات
    buttons_raw = None if msg.text.strip().lower() in ["تخطي", "skip"] else msg.text.strip()
    await add_template(
        data["template_name"],
        data["content"],
        data.get("media_path"),
        data.get("media_type"),
        buttons_raw   # ← كان ناقصاً
    )
    await state.clear()
    await msg.answer(f"✅ تم حفظ القالب <b>{data['template_name']}</b>", parse_mode="HTML")

@router.callback_query(F.data == "delete_template")
async def cb_delete_template(cb: CallbackQuery):
    templates = await get_all_templates()
    if not templates:
        await cb.answer("لا توجد قوالب!", show_alert=True)
        return
    buttons = [[InlineKeyboardButton(
        text=f"🗑 {t[1]}", callback_data=f"confirm_del_template_{t[1]}"
    )] for t in templates]
    buttons.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="templates_menu")])
    await cb.message.edit_text("اختر القالب للحذف:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("confirm_del_template_"))
async def cb_confirm_del_template(cb: CallbackQuery):
    name = cb.data[len("confirm_del_template_"):]
    await delete_template(name)
    await cb.answer(f"✅ تم حذف {name}")
    await cb_delete_template(cb)

# ─── Scheduling ───────────────────────────────────────────
@router.callback_query(F.data == "schedule_menu")
async def cb_schedule_menu(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    scheduled = await get_scheduled()
    text = "⏰ <b>الجدولة:</b>\n\n"
    for s in scheduled:
        text += f"• <b>{s[1]}</b> | 🕐 {s[2]} | 🔁 {s[3]}د\n"
    if not scheduled:
        text += "لا توجد جدولة نشطة."

    buttons = [[InlineKeyboardButton(text="➕ جدولة جديدة", callback_data="add_schedule")]]
    for s in scheduled:
        buttons.append([InlineKeyboardButton(
            text=f"🗑 {s[1]} @ {s[2]}", callback_data=f"del_schedule_{s[0]}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")])

    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data == "add_schedule")
async def cb_add_schedule(cb: CallbackQuery, state: FSMContext):
    templates = await get_all_templates()
    if not templates:
        await cb.answer("أضف قوالب أولاً!", show_alert=True)
        return
    buttons = [[InlineKeyboardButton(
        text=f"🧩 {t[1]}", callback_data=f"sched_tmpl_{t[1]}"
    )] for t in templates]
    buttons.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="schedule_menu")])
    await cb.message.edit_text("اختر القالب للجدولة:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("sched_tmpl_"))
async def cb_sched_template(cb: CallbackQuery, state: FSMContext):
    name = cb.data[len("sched_tmpl_"):]
    await state.update_data(sched_template=name)
    await state.set_state(BroadcastStates.waiting_schedule_time)
    await cb.message.edit_text(
        "أرسل وقت الإرسال (HH:MM) مثال: <code>14:30</code>",
        reply_markup=back_button("schedule_menu"),
        parse_mode="HTML"
    )

@router.message(BroadcastStates.waiting_schedule_time)
async def process_schedule_time(msg: Message, state: FSMContext):
    time_str = msg.text.strip()
    if not re.match(r"^\d{2}:\d{2}$", time_str):
        await msg.answer("❌ صيغة غير صحيحة. أرسل مثل: 14:30")
        return
    await state.update_data(sched_time=time_str)
    await state.set_state(BroadcastStates.waiting_schedule_interval)
    await msg.answer(
        "أرسل فترة التكرار بالدقائق (0 = مرة واحدة):\n"
        "مثال: <code>60</code> = كل ساعة",
        parse_mode="HTML"
    )

@router.message(BroadcastStates.waiting_schedule_interval)
async def process_schedule_interval(msg: Message, state: FSMContext):
    try:
        interval = int(msg.text.strip())
    except ValueError:
        interval = 0
    data = await state.get_data()
    await state.clear()
    await add_scheduled(data["sched_template"], data["sched_time"], interval)
    # FIX: بناء الرسالة بشكل صحيح بدل ternary داخل f-string
    if interval:
        text = (
            f"✅ تم جدولة <b>{data['sched_template']}</b>\n"
            f"🕐 الوقت: {data['sched_time']}\n"
            f"🔁 كل: {interval} دقيقة"
        )
    else:
        text = f"✅ مرة واحدة عند {data['sched_time']}"
    await msg.answer(text, parse_mode="HTML")

@router.callback_query(F.data.startswith("del_schedule_"))
async def cb_del_schedule(cb: CallbackQuery):
    sid = int(cb.data.split("_")[-1])
    await remove_scheduled(sid)
    await cb.answer("✅ تم الحذف")
    await cb_schedule_menu(cb)
