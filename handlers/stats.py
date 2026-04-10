from aiogram import Router, F
from aiogram.types import CallbackQuery
from utils.helpers import is_admin, is_feature_allowed, back_button
from database.db import get_stats

router = Router()

@router.callback_query(F.data == "stats_menu")
async def cb_stats(cb: CallbackQuery):
    if not await is_feature_allowed(cb.from_user.id, "stats_view"):
        await cb.answer("⛔ هذه الخدمة غير متاحة حالياً.", show_alert=True)
        return
    s = await get_stats()
    text = (
        "📊 <b>الإحصائيات:</b>\n\n"
        f"👥 الكروبات النشطة: <b>{s['active_groups']}</b> / {s['total_groups']}\n"
        f"🧩 القوالب: <b>{s['templates']}</b>\n"
        f"🤖 الردود التلقائية: <b>{s['auto_replies']}</b>\n"
        f"📢 إجمالي البثات: <b>{s['total_broadcasts']}</b>\n"
        f"✉️ إجمالي الرسائل المرسلة: <b>{s['total_sent']}</b>\n"
        f"🚫 محظورون: <b>{s['blacklisted']}</b>\n"
        f"👮 المشرفون: <b>{s['admins']}</b>"
    )
    await cb.message.edit_text(text, reply_markup=back_button("main_menu"), parse_mode="HTML")
