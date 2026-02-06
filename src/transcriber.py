import io
import asyncio
from mistralai import Mistral
from .config import Config
from .logger import setup_logger

logger = setup_logger("Transcriber")

class MistralTranscriber:
    def __init__(self):
        # Инициализируем клиент Mistral
        self.client = Mistral(api_key=Config.MISTRAL_API_KEY)
        # Используем новейшую модель, которая показала лучшие результаты
        self.model = "voxtral-mini-2602"

    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Основной метод для вызова из Userbot. 
        Запускает блокирующую сетевую операцию в отдельном потоке.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, audio_bytes)

    def _transcribe_sync(self, audio_bytes: bytes) -> str:
        """
        Синхронная логика взаимодействия с Audio API.
        """
        try:
            logger.info(f"Начало транскрипции через Audio API (Model: {self.model})...")
            
            # Подготовка "виртуального" файла в оперативной памяти
            audio_file = io.BytesIO(audio_bytes)
            # Имя файла помогает API определить формат (ogg/opus для Telegram)
            audio_file.name = "voice.ogg"

            # Прямой вызов специализированного метода транскрипции
            # Этот метод автоматически обрабатывает загрузку и возвращает результат
            response = self.client.audio.transcriptions.complete(
                model=self.model,
                file={
                    "content": audio_file,
                    "file_name": audio_file.name,
                }
            )

            # Извлечение текста. SDK Mistral возвращает объект, 
            # где текст лежит в атрибуте .text
            if hasattr(response, 'text'):
                result = response.text
            else:
                # Резервный вариант на случай изменений в структуре ответа SDK
                result = str(response)

            if not result or not result.strip():
                logger.warning("API вернуло пустой результат (возможно, тишина в аудио).")
                return "Голосовое сообщение распознано как пустое."

            logger.info(f"Транскрипция успешно завершена (символов: {len(result)})")
            return result

        except Exception as e:
            # Детальное логирование ошибки для отладки
            logger.error(f"Критическая ошибка Audio API: {e}", exc_info=True)
            return f"❌ Ошибка при распознавании: {str(e)}"