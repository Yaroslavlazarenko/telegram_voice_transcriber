import base64
import asyncio
from mistralai import Mistral
from .config import Config
from .logger import setup_logger

logger = setup_logger("Transcriber")

class MistralTranscriber:
    def __init__(self):
        self.client = Mistral(api_key=Config.MISTRAL_API_KEY)
        self.model = Config.MISTRAL_MODEL

    async def transcribe(self, audio_bytes: bytes) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, audio_bytes)

    def _transcribe_sync(self, audio_bytes: bytes) -> str:
        try:
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

            messages_payload = []

            if Config.SYSTEM_PROMPT:
                messages_payload.append({
                    "role": "system", 
                    "content": Config.SYSTEM_PROMPT
                })

            final_text_prompt = Config.TRANSCRIBE_PROMPT
            if Config.TARGET_LANGUAGE and Config.TARGET_LANGUAGE.strip():
                final_text_prompt += f"\nТвоя транскрипция должна быть на языке: {Config.TARGET_LANGUAGE}. Не имеет значения какой язык использовался в аудио, ты в результате должен перевести на {Config.TARGET_LANGUAGE}."

            user_content = [
                {
                    "type": "input_audio",
                    "input_audio": audio_base64
                },
                {
                    "type": "text",
                    "text": final_text_prompt
                }
            ]

            messages_payload.append({
                "role": "user",
                "content": user_content
            })

            logger.info(f"Отправка запроса в Mistral (Model: {self.model}, Size: {len(audio_bytes)} bytes)...")
            
            chat_response = self.client.chat.complete(
                model=self.model,
                messages=messages_payload
            )
            
            result = chat_response.choices[0].message.content
            logger.info("Ответ от Mistral получен успешно.")
            return result

        except Exception as e:
            logger.error(f"Ошибка транскрипции: {e}", exc_info=True)
            return f"Ошибка транскрипции: {str(e)}"