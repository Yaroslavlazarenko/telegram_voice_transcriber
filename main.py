import asyncio
from src.userbot import Userbot
from src.logger import setup_logger

logger = setup_logger("Main")

if __name__ == '__main__':
    bot = Userbot()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем.")