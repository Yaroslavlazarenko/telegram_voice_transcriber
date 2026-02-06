import io
import asyncio
import qrcode
import html
from telethon import TelegramClient, events, types, functions, utils
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
        self.MAX_MSG_LEN = 4000 # Лимит с запасом

    async def start(self):
        await self.client.connect()
        if not await self.client.is_user_authorized():
            logger.info("Генерация QR-кода...")
            qr_login = await self.client.qr_login()
            qr = qrcode.QRCode()
            qr.add_data(qr_login.url)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
            await qr_login.wait()

        me = await self.client.get_me()
        self.my_id = me.id
        logger.info(f"Userbot запущен (ID: {self.my_id})")

        self.client.add_event_handler(self.reaction_handler, events.Raw())
        await self.client.run_until_disconnected()

    async def reaction_handler(self, event):
        if not isinstance(event, types.UpdateEditMessage): return
        if not event.message or not event.message.reactions: return

        msg = event.message
        target_found = False
        reactions_to_keep = []

        if msg.reactions.recent_reactions:
            for r in msg.reactions.recent_reactions:
                uid = r.peer_id.user_id if isinstance(r.peer_id, types.PeerUser) else None
                if uid == self.my_id:
                    emoji = r.reaction.emoticon if isinstance(r.reaction, types.ReactionEmoji) else None
                    if emoji == Config.TRIGGER_EMOJI:
                        target_found = True
                    else:
                        reactions_to_keep.append(r.reaction)

        if target_found:
            try:
                await self.client(functions.messages.SendReactionRequest(
                    peer=msg.peer_id, msg_id=msg.id, reaction=reactions_to_keep
                ))
            except: pass
            asyncio.create_task(self._process_media(msg.peer_id, msg.id))

    def _get_msg_link(self, chat, msg_id):
        try:
            if hasattr(chat, 'username') and chat.username:
                return f"https://t.me/{chat.username}/{msg_id}"
            chat_id = str(chat.id).replace("-100", "")
            return f"https://t.me/c/{chat_id}/{msg_id}"
        except: return None

    async def _process_media(self, peer, msg_id):
        try:
            m = await self.client.get_messages(peer, ids=msg_id)
            if not m or not (m.voice or m.video_note): return

            is_video = bool(m.video_note)
            ext = "video.mp4" if is_video else "voice.ogg"
            label = "Кружочек" if is_video else "Голосовое"

            chat = await m.get_chat()
            sender = await m.get_sender()
            chat_title = getattr(chat, 'title', 'Личные сообщения')
            sender_name = utils.get_display_name(sender) if sender else "Неизвестный"

            logger.info(f"Скачивание {label} от {sender_name}...")
            file_bytes = io.BytesIO()
            await self.client.download_media(m, file=file_bytes)
            
            # 1. Получаем полный текст транскрипции
            raw_text = await self.transcriber.transcribe(file_bytes.getvalue(), ext)
            
            # Экранируем спецсимволы
            safe_chat = html.escape(chat_title)
            safe_sender = html.escape(sender_name)
            safe_text = html.escape(raw_text)
            
            # 2. Формируем "шапку" описания
            header = (
                f"<b>Чат:</b> {safe_chat}\n"
                f"<b>От:</b> {safe_sender}\n"
                f"<b>Тип:</b> {label}\n"
                f"--------------------\n\n"
            )
            
            msg_link = self._get_msg_link(chat, msg_id)
            
            # 3. Логика разбивки на части
            parts = []
            
            if len(header + safe_text) <= self.MAX_MSG_LEN:
                # Всё влезает в одно сообщение
                parts.append(header + safe_text)
            else:
                # В первое сообщение кладем шапку и сколько влезет текста
                space_in_first = self.MAX_MSG_LEN - len(header)
                parts.append(header + safe_text[:space_in_first])
                
                # Остальной текст режем на куски по MAX_MSG_LEN
                remaining_text = safe_text[space_in_first:]
                for i in range(0, len(remaining_text), self.MAX_MSG_LEN):
                    parts.append(remaining_text[i : i + self.MAX_MSG_LEN])

            # 4. Отправка частей
            for i, part_content in enumerate(parts):
                is_last = (i == len(parts) - 1)
                
                # Кнопку прикрепляем только к последней части
                btn_text = "🔗 Перейти к сообщению" if is_last else None
                btn_url = msg_link if is_last else None
                
                await self.bot_sender.send_message(
                    chat_id=self.my_id,
                    text=part_content,
                    button_text=btn_text,
                    button_url=btn_url
                )
                
                # Небольшая пауза между отправками, чтобы Telegram не забанил за спам
                if not is_last:
                    await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Ошибка в _process_media: {e}", exc_info=True)