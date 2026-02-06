import io
import asyncio
from mistralai import Mistral
from .config import Config
from .logger import setup_logger

logger = setup_logger("Transcriber")

class MistralTranscriber:
    def __init__(self):
        self.client = Mistral(api_key=Config.MISTRAL_API_KEY)
        # Важно: используем модель, которую вы указали
        self.model = Config.MISTRAL_MODEL or "voxtral-small-latest"

    async def transcribe(self, audio_bytes: bytes) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, audio_bytes)

    def _transcribe_sync(self, audio_bytes: bytes) -> str:
        uploaded_audio = None
        try:
            logger.info(f"Начало обработки аудио (размер: {len(audio_bytes)} байт)...")

            # 1. Подготовка файла в памяти (имитация реального файла)
            file_obj = io.BytesIO(audio_bytes)
            # Имя нужно, чтобы Mistral понял формат (ogg - стандарт Telegram)
            file_obj.name = "voice_message.ogg" 

            # 2. Загрузка файла в Mistral Storage
            logger.info("Загрузка файла на сервер Mistral...")
            uploaded_audio = self.client.files.upload(
                file={
                    "content": file_obj,
                    "file_name": file_obj.name
                },
                purpose="m_audio" # Для аудио моделей часто используется этот purpose или просто "fine-tune", но пробуем по умолчанию или как в примере
            )
            
            # 3. Получение временной ссылки (Signed URL)
            logger.info(f"Файл загружен (ID: {uploaded_audio.id}). Получение ссылки...")
            signed_url = self.client.files.get_signed_url(file_id=uploaded_audio.id)

            # 4. Формирование запроса
            messages_payload = []

            # Системный промпт (инструкция)
            if Config.SYSTEM_PROMPT:
                messages_payload.append({
                    "role": "system", 
                    "content": Config.SYSTEM_PROMPT
                })

            # Промпт для транскрипции
            final_text = Config.TRANSCRIBE_PROMPT
            if Config.TARGET_LANGUAGE:
                final_text += f"\nОтвет дай на языке: {Config.TARGET_LANGUAGE}."

            user_content = [
                {
                    "type": "input_audio",
                    "input_audio": signed_url.url,
                },
                {
                    "type": "text",
                    "text": final_text
                }
            ]

            messages_payload.append({
                "role": "user",
                "content": user_content
            })

            # 5. Отправка в чат
            logger.info(f"Отправка запроса в модель {self.model}...")
            chat_response = self.client.chat.complete(
                model=self.model,
                messages=messages_payload
            )
            
            result = chat_response.choices[0].message.content
            logger.info("Ответ получен успешно.")
            
            return result

        except Exception as e:
            logger.error(f"Ошибка транскрипции Mistral: {e}", exc_info=True)
            return f"Ошибка транскрипции: {str(e)}"
        
        finally:
            # (Опционально) Удаляем файл из облака Mistral, чтобы не мусорить
            if uploaded_audio and hasattr(uploaded_audio, 'id'):
                try:
                    self.client.files.delete(file_id=uploaded_audio.id)
                    logger.info("Временный файл удален из Mistral.")
                except Exception as cleanup_error:
                    logger.warning(f"Не удалось удалить файл: {cleanup_error}")