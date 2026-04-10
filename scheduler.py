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

async def send_to_groups(bot: Bot, groups: list, data: dict, delay: float = 0.5):
    import os
    from database.db import get_session
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    sent = failed = 0

    session_row = await get_session()
    if not session_row:
        logger.warning("No session found, skipping broadcast")
        return 0, len(groups)

    api_id   = int(os.environ.get("API_ID", "0"))
    api_hash = os.environ.get("API_HASH", "")

    try:
        client = TelegramClient(StringSession(session_row[0]), api_id, api_hash)
        await client.connect()
    except Exception as e:
        logger.error(f"Telethon connect error: {e}")
        return 0, len(groups)

    for group_id, title in groups:
        try:
            text = data.get("text", "")
            if data.get("photo"):
                await client.send_file(int(group_id), data["photo"], caption=text)
            elif data.get("video"):
                await client.send_file(int(group_id), data["video"], caption=text)
            else:
                await client.send_message(int(group_id), text, parse_mode="html")
            sent += 1
        except Exception as e:
            logger.warning(f"Failed to send to {group_id} ({title}): {e}")
            failed += 1
        await asyncio.sleep(delay)

    await client.disconnect()
    return sent, failed

async def run_scheduler(bot: Bot):
    logger.info("⏰ Scheduler started")
    while True:
        try:
            now = datetime.now().strftime("%H:%M")
            scheduled = await get_scheduled()

            for s in scheduled:
                sid            = s[0]
                template_name  = s[1]
                schedule_time  = s[2]
                repeat_interval = s[3]
                # s[5] = msg_count, s[6] = msg_delay
                msg_count = s[5] if len(s) > 5 and s[5] else 0
                msg_delay = s[6] if len(s) > 6 and s[6] else 30

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

                # تطبيق حد الرسائل
                if msg_count and msg_count < len(groups):
                    groups = groups[:msg_count]

                buttons_markup = parse_buttons(tmpl[5]) if len(tmpl) > 5 and tmpl[5] else None
                data = {
                    "text":    tmpl[2],
                    "buttons": buttons_markup,
                    "photo":   tmpl[3] if tmpl[4] == "photo" else None,
                    "video":   tmpl[3] if tmpl[4] == "video" else None,
                }

                sent, failed = await send_to_groups(bot, groups, data, delay=msg_delay)
                await log_broadcast(template_name, sent, failed)
                logger.info(f"✅ Scheduled broadcast done: sent={sent} failed={failed}")
                logger.info(f"✅ Scheduled broadcast done: sent={sent} failed={failed}")

                # إذا مو متكرر احذفه
                if repeat_interval == 0:
                    await remove_scheduled(sid)

        except Exception as e:
            logger.error(f"Scheduler error: {e}")

        await asyncio.sleep(60)  # تحقق كل دقيقة
