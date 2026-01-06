import io
import asyncio
import qrcode
from telethon import TelegramClient, events, types, functions
from telethon.errors import SessionPasswordNeededError
from .config import Config
from .transcriber import MistralTranscriber
from .bot_sender import BotSender
from .logger import setup_logger

logger = setup_logger("Userbot")

class Userbot:
    def __init__(self):
        self.client = TelegramClient(Config.SESSION_NAME, Config.API_ID, Config.API_HASH)
        self.transcriber = MistralTranscriber()
        self.bot_sender = BotSender()
        self.my_id = None

    async def start(self):
        logger.info("Подключение Userbot...")
        await self.client.connect()

        # Проверка авторизации. Если нет сессии — запускаем QR логин
        if not await self.client.is_user_authorized():
            try:
                logger.info("Сессия не найдена. Генерирую QR-код для входа...")
                qr_login = await self.client.qr_login()
                
                # Генерация и вывод QR-кода в консоль
                qr = qrcode.QRCode()
                qr.add_data(qr_login.url)
                qr.make(fit=True)
                
                print("\n" + "="*40)
                # invert=True делает QR-код читаемым на темных фонах терминала
                qr.print_ascii(invert=True)
                print("="*40 + "\n")
                
                logger.info("Отсканируйте QR-код выше (Настройки -> Устройства -> Подключить устройство)")
                
                # Ожидание сканирования
                await qr_login.wait()
                logger.info("Вход выполнен успешно!")

            except SessionPasswordNeededError:
                # Если стоит 2FA (облачный пароль)
                pw = input("Введите ваш облачный пароль (2FA): ")
                await self.client.sign_in(password=pw)
            except Exception as e:
                logger.error(f"Ошибка входа по QR: {e}")
                logger.info("Переключаюсь на стандартный вход (номер телефона)...")
                await self.client.start()

        # Получаем информацию о себе
        me = await self.client.get_me()
        self.my_id = me.id
        logger.info(f"Userbot запущен (ID: {self.my_id})")
        logger.info(f"Ожидаю реакцию '{Config.TRIGGER_EMOJI}'...")

        self.client.add_event_handler(self.reaction_handler, events.Raw())
        
        await self.client.run_until_disconnected()

    async def reaction_handler(self, event):
        reactions_list = []
        peer = None
        msg_id = None
        
        if isinstance(event, types.UpdateEditMessage):
            if event.message:
                peer = event.message.peer_id
                msg_id = event.message.id
                if event.message.reactions and event.message.reactions.recent_reactions:
                    reactions_list = event.message.reactions.recent_reactions

        if not reactions_list:
            return

        target_found = False
        reactions_to_keep = [] 
        
        for reaction in reactions_list:
            peer_id = None
            if isinstance(reaction.peer_id, types.PeerUser):
                peer_id = reaction.peer_id.user_id
            
            # Проверяем, что реакция поставлена нами
            if peer_id == self.my_id:
                emoji = None
                if isinstance(reaction.reaction, types.ReactionEmoji):
                    emoji = reaction.reaction.emoticon
                
                if emoji == Config.TRIGGER_EMOJI:
                    logger.info(f"НАЙДЕНА РЕАКЦИЯ {Config.TRIGGER_EMOJI} в сообщении {msg_id}!")
                    target_found = True
                else:
                    reactions_to_keep.append(reaction.reaction)

        if target_found:
            await self._remove_reaction(peer, msg_id, reactions_to_keep)
            asyncio.create_task(self._process_voice(peer, msg_id))

    async def _remove_reaction(self, peer, msg_id, reactions_to_keep):
        logger.info("Попытка удаления реакции...")
        try:
            await self.client(functions.messages.SendReactionRequest(
                peer=peer,
                msg_id=msg_id,
                reaction=reactions_to_keep 
            ))
            logger.info("Реакция успешно удалена.")
        except Exception as e:
            logger.error(f"Не удалось удалить реакцию: {e}")

    async def _process_voice(self, peer, msg_id):
        try:
            message = await self.client.get_messages(peer, ids=msg_id)
            
            if message and (message.voice or message.round_message):
                media_type = "Голосовое" if message.voice else "Видеосообщение"
                logger.info(f"{media_type} найдено. Начинаю скачивание в память...")
                
                file_bytes = io.BytesIO()
                
                await self.client.download_media(message, file=file_bytes)
                
                audio_data = file_bytes.getvalue()
                logger.info(f"Скачано {len(audio_data)} байт. Передаю в Mistral...")

                text = await self.transcriber.transcribe(audio_data)
                logger.info("Транскрипция завершена.")

                header = f"🎤 Расшифровка ({media_type}) (ID: {msg_id})\n\n"
                
                await self.bot_sender.send_message(self.my_id, header + text)

            elif message:
                logger.warning("Сообщение найдено, но в нем нет голосового или кружочка.")
            else:
                logger.warning("Не удалось получить объект сообщения по ID.")

        except Exception as e:
            logger.error(f"Критическая ошибка обработки: {e}", exc_info=True)