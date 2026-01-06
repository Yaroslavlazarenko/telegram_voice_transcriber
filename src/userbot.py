import io
import asyncio
import qrcode
from telethon import TelegramClient, events, types, functions, utils
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

        if not await self.client.is_user_authorized():
            try:
                logger.info("Сессия не найдена. Генерирую QR-код...")
                qr_login = await self.client.qr_login()
                
                qr = qrcode.QRCode()
                qr.add_data(qr_login.url)
                qr.make(fit=True)
                
                print("\n" + "="*40)
                qr.print_ascii(invert=True)
                print("="*40 + "\n")
                
                logger.info("Отсканируйте QR-код выше.")
                await qr_login.wait()
                logger.info("Вход выполнен успешно!")

            except SessionPasswordNeededError:
                pw = input("Введите ваш облачный пароль (2FA): ")
                await self.client.sign_in(password=pw)
            except Exception as e:
                logger.error(f"Ошибка входа по QR: {e}")
                await self.client.start()

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
            
            if peer_id == self.my_id:
                emoji = None
                if isinstance(reaction.reaction, types.ReactionEmoji):
                    emoji = reaction.reaction.emoticon
                
                if emoji == Config.TRIGGER_EMOJI:
                    target_found = True
                else:
                    reactions_to_keep.append(reaction.reaction)

        if target_found:
            await self._remove_reaction(peer, msg_id, reactions_to_keep)
            asyncio.create_task(self._process_voice(peer, msg_id))

    async def _remove_reaction(self, peer, msg_id, reactions_to_keep):
        try:
            await self.client(functions.messages.SendReactionRequest(
                peer=peer,
                msg_id=msg_id,
                reaction=reactions_to_keep 
            ))
        except Exception:
            pass

    async def _process_voice(self, peer, msg_id):
        try:
            message = await self.client.get_messages(peer, ids=msg_id)
            
            if message and (message.voice or message.round_message):
                logger.info(f"Начало обработки сообщения {msg_id}...")

                # 1. Получаем информацию о чате
                chat = await message.get_chat()
                # Если у чата есть атрибут title (группа/канал), берем его. Иначе - это ЛС.
                chat_title = getattr(chat, 'title', 'Личные сообщения')

                # 2. Получаем информацию об отправителе
                sender = await message.get_sender()
                sender_name = "Неизвестный"
                username_str = ""

                if sender:
                    sender_name = utils.get_display_name(sender)
                    if hasattr(sender, 'username') and sender.username:
                        username_str = f"(@{sender.username})"

                # 3. Скачиваем аудио
                file_bytes = io.BytesIO()
                await self.client.download_media(message, file=file_bytes)
                audio_data = file_bytes.getvalue()

                # 4. Транскрибируем
                text = await self.transcriber.transcribe(audio_data)

                # 5. Формируем сообщение (Обычный текст без HTML)
                response_text = (
                    f"Чат: {chat_title}\n"
                    f"От: {sender_name} {username_str}\n"
                    f"--------------------\n\n"
                    f"{text}"
                )
                
                await self.bot_sender.send_message(self.my_id, response_text)

            elif message:
                logger.warning("Сообщение не содержит голосового или видео.")

        except Exception as e:
            logger.error(f"Ошибка обработки: {e}", exc_info=True)