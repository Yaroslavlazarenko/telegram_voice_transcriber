import asyncio
from src.userbot import Userbot
from src.logger import setup_logger

logger = setup_logger("Main")

if __name__ == '__main__':
    logger.info("Инициализация программы...")
    bot = Userbot()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Программа остановлена пользователем.")
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске: {e}", exc_info=True)