"""
scheduler.py
يشغّل البث المجدول تلقائياً في الخلفية
"""

import asyncio
import logging
from datetime import datetime
from aiogram import Bot
from database.db import get_scheduled, remove_scheduled, get_template, get_active_groups, log_broadcast
from utils.helpers import parse_buttons

logger = logging.getLogger(__name__)

async def send_to_groups(bot: Bot, groups: list, data: dict, delay: float = 0.3):
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
        except Exception as e:
            logger.warning(f"Failed to send to {group_id}: {e}")
            failed += 1
        await asyncio.sleep(delay)
    return sent, failed

async def run_scheduler(bot: Bot):
    logger.info("⏰ Scheduler started")
    while True:
        try:
            now = datetime.now().strftime("%H:%M")
            scheduled = await get_scheduled()

            for s in scheduled:
                sid, template_name, schedule_time, repeat_interval, active = s[0], s[1], s[2], s[3], s[4]

                if schedule_time != now:
                    continue

                logger.info(f"⏰ Running scheduled broadcast: {template_name}")
                tmpl = await get_template(template_name)
                if not tmpl:
                    logger.warning(f"Template {template_name} not found, removing schedule")
                    await remove_scheduled(sid)
                    continue

                groups = await get_active_groups()
                if not groups:
                    logger.warning("No active groups for scheduled broadcast")
                    continue

                buttons_markup = parse_buttons(tmpl[5]) if len(tmpl) > 5 and tmpl[5] else None
                data = {
                    "text": tmpl[2],
                    "buttons": buttons_markup,
                    "photo": tmpl[3] if tmpl[4] == "photo" else None,
                    "video": tmpl[3] if tmpl[4] == "video" else None,
                }

                sent, failed = await send_to_groups(bot, groups, data)
                await log_broadcast(template_name, sent, failed)
                logger.info(f"✅ Scheduled broadcast done: sent={sent} failed={failed}")

                # إذا مو متكرر احذفه
                if repeat_interval == 0:
                    await remove_scheduled(sid)

        except Exception as e:
            logger.error(f"Scheduler error: {e}")

        await asyncio.sleep(60)  # تحقق كل دقيقة
