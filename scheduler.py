import asyncio
import logging
import os
from datetime import datetime
from aiogram import Bot
from database.db import get_scheduled, remove_scheduled, get_template, get_active_groups, log_broadcast
from utils.helpers import parse_buttons

logger = logging.getLogger(__name__)

# تتبع الـ tasks الشغالة: sid → task
_active_tasks: dict = {}


async def _get_telethon_client():
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from database.db import get_session

    session_row = await get_session()
    if not session_row:
        return None

    api_id   = int(os.environ.get("API_ID", "0"))
    api_hash = os.environ.get("API_HASH", "")

    try:
        client = TelegramClient(StringSession(session_row[0]), api_id, api_hash)
        await client.connect()
        return client
    except Exception as e:
        logger.error(f"Telethon connect error: {e}")
        return None


async def _send_once(groups: list, data: dict) -> tuple[int, int]:
    """يرسل رسالة وحدة لكل القروبات"""
    client = await _get_telethon_client()
    if not client:
        return 0, len(groups)

    sent = failed = 0
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
            logger.warning(f"Failed {group_id}: {e}")
            failed += 1
        await asyncio.sleep(1)

    await client.disconnect()
    return sent, failed


async def _repeater_task(sid: int, template_name: str, msg_count: int, msg_delay: int):
    """
    loop مستمر — يرسل لكل القروبات ثم ينتظر msg_delay ثانية
    يكرر msg_count مرة (0 = بلا حد)
    """
    logger.info(f"▶ بدء: {template_name} | {msg_count} مرة | كل {msg_delay}ث")

    total_sent = total_failed = 0
    count = 0

    while True:
        try:
            # توقف لو وصل الحد
            if msg_count > 0 and count >= msg_count:
                break

            tmpl = await get_template(template_name)
            if not tmpl:
                logger.warning(f"القالب {template_name} غير موجود")
                break

            groups = await get_active_groups()
            if not groups:
                logger.warning("لا توجد قروبات")
                break

            buttons_markup = parse_buttons(tmpl[5]) if len(tmpl) > 5 and tmpl[5] else None
            data = {
                "text":    tmpl[2],
                "buttons": buttons_markup,
                "photo":   tmpl[3] if tmpl[4] == "photo" else None,
                "video":   tmpl[3] if tmpl[4] == "video" else None,
            }

            sent, failed  = await _send_once(groups, data)
            total_sent   += sent
            total_failed += failed
            count        += 1
            logger.info(f"إرسال {count}/{msg_count if msg_count else '∞'} — نجح={sent} فشل={failed}")

            # انتظر قبل الجولة التالية
            await asyncio.sleep(msg_delay)

        except asyncio.CancelledError:
            logger.info(f"تم إيقاف: {template_name}")
            break
        except Exception as e:
            logger.error(f"خطأ: {e}")
            await asyncio.sleep(10)

    await log_broadcast(template_name, total_sent, total_failed)
    logger.info(f"✅ انتهى: {template_name} total={total_sent}")
    _active_tasks.pop(sid, None)


async def run_scheduler(bot: Bot):
    logger.info("⏰ Scheduler started")
    while True:
        try:
            now = datetime.now().strftime("%H:%M")
            scheduled = await get_scheduled()

            for s in scheduled:
                sid             = s[0]
                template_name   = s[1]
                schedule_time   = s[2]
                repeat_interval = s[3]
                msg_count       = s[5] if len(s) > 5 and s[5] is not None else 1
                msg_delay       = s[6] if len(s) > 6 and s[6] is not None else 300

                if schedule_time != now:
                    continue

                # لا تشغل نفس الجدولة مرتين
                if sid in _active_tasks:
                    continue

                logger.info(f"⏰ تشغيل جدولة: {template_name}")
                task = asyncio.create_task(
                    _repeater_task(sid, template_name, msg_count, msg_delay)
                )
                _active_tasks[sid] = task

                if repeat_interval == 0:
                    await remove_scheduled(sid)

        except Exception as e:
            logger.error(f"Scheduler error: {e}")

        await asyncio.sleep(60)
