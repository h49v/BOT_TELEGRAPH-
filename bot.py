import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from handlers import admin, groups, broadcast, auto_reply, stats, backup, sessions
from database.db import init_db
from scheduler import run_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def main():
    await init_db()

    bot = Bot(token=os.environ["BOT_TOKEN"])
    dp  = Dispatcher(storage=MemoryStorage())

    dp.include_router(admin.router)
    dp.include_router(sessions.router)
    dp.include_router(groups.router)
    dp.include_router(broadcast.router)
    dp.include_router(auto_reply.router)
    dp.include_router(stats.router)
    dp.include_router(backup.router)

    # شغّل الـ scheduler في الخلفية
    asyncio.create_task(run_scheduler(bot))

    logger.info("🤖 CyberBand Bot starting...")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"])

if __name__ == "__main__":
    asyncio.run(main())
