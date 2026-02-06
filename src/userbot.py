import io
import asyncio
import qrcode
import html
import uuid
from telethon import TelegramClient, events, types, functions, utils, Button
from .config import Config
from .transcriber import MistralTranscriber
from .text_fixer import MistralTextFixer
from .bot_sender import BotSender
from .logger import setup_logger

logger = setup_logger("Userbot")

class Userbot:
    def __init__(self):
        self.client = TelegramClient(Config.SESSION_NAME, Config.API_ID, Config.API_HASH)
        self.bot_client = TelegramClient("bot_session", Config.API_ID, Config.API_HASH)
        
        self.transcriber = MistralTranscriber()
        self.fixer = MistralTextFixer()
        self.bot_sender = BotSender()
        
        self.my_id = None
        self.fix_cache = {} # Храним данные правок

    async def start(self):
        # Запуск Юзербота
        await self.client.connect()
        if not await self.client.is_user_authorized():
            qr_login = await self.client.qr_login()
            qr = qrcode.QRCode()
            qr.add_data(qr_login.url)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
            await qr_login.wait()

        # Запуск Бота
        await self.bot_client.start(bot_token=Config.BOT_TOKEN)
        
        me = await self.client.get_me()
        self.my_id = me.id
        logger.info(f"Бот и Юзербот запущены. ID: {self.my_id}")

        self.client.add_event_handler(self.reaction_handler, events.Raw())
        self.bot_client.add_event_handler(self.bot_callback_handler, events.CallbackQuery())
        
        await self.client.run_until_disconnected()

    async def reaction_handler(self, event):
        if not isinstance(event, types.UpdateEditMessage): return
        msg = event.message
        if not msg or not msg.reactions: return

        target_found = False
        others = []
        for r in msg.reactions.recent_reactions:
            uid = r.peer_id.user_id if isinstance(r.peer_id, types.PeerUser) else None
            if uid == self.my_id:
                emoji = r.reaction.emoticon if isinstance(r.reaction, types.ReactionEmoji) else None
                if emoji == Config.TRIGGER_EMOJI: target_found = True
                else: others.append(r.reaction)

        if target_found:
            try:
                await self.client(functions.messages.SendReactionRequest(
                    peer=msg.peer_id, msg_id=msg.id, reaction=others
                ))
            except: pass
            
            # Если это аудио/видео
            if msg.voice or msg.video_note:
                asyncio.create_task(self._process_media(msg.peer_id, msg.id))
            # Если это текст
            elif msg.text:
                asyncio.create_task(self._process_text_fix(msg.peer_id, msg.id, msg.text))

    async def _process_text_fix(self, peer, msg_id, text):
        try:
            fixed = await self.fixer.fix_punctuation(text)
            if fixed.strip() == text.strip(): return

            fix_id = str(uuid.uuid4())[:8]
            chat = await self.client.get_entity(peer)
            
            # Сохраняем в кэш
            self.fix_cache[fix_id] = {
                "peer": peer,
                "msg_id": msg_id,
                "text": fixed,
                "link": self._get_link(chat, msg_id)
            }

            diff = (
                f"📝 <b>Коррекция пунктуации</b>\n\n"
                f"❌ <b>Было:</b>\n<code>{html.escape(text)}</code>\n\n"
                f"✅ <b>Стало:</b>\n<code>{html.escape(fixed)}</code>"
            )

            await self.bot_sender.send_message(
                chat_id=self.my_id,
                text=diff,
                button_text="Применить ✅",
                button_url=f"fix:{fix_id}"
            )
        except Exception as e:
            logger.error(f"Ошибка коррекции: {e}")

    async def bot_callback_handler(self, event):
        data = event.data.decode()
        if not data.startswith("fix:"): return
        
        fix_id = data.split(":")[1]
        fix_data = self.fix_cache.get(fix_id)
        
        if fix_data:
            try:
                # 1. Редактируем сообщение через Юзербота
                await self.client.edit_message(
                    fix_data["peer"], 
                    fix_data["msg_id"], 
                    fix_data["text"]
                )
                
                # 2. Обновляем сообщение бота: текст успеха + кнопка-ссылка назад
                await event.edit(
                    f"✅ <b>Сообщение отредактировано!</b>\n\n"
                    f"Текст успешно исправлен и заменен в чате.",
                    buttons=[Button.url("🔗 Вернуться к сообщению", fix_data["link"])]
                )
                del self.fix_cache[fix_id]
            except Exception as e:
                logger.error(f"Ошибка применения: {e}")
                await event.answer("Ошибка: не удалось отредактировать сообщение.", alert=True)
        else:
            await event.answer("Ошибка: данные устарели.", alert=True)

    # --- ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ (Транскрипция и Ссылки) ---

    def _get_link(self, chat, msg_id):
        try:
            if hasattr(chat, 'username') and chat.username:
                return f"https://t.me/{chat.username}/{msg_id}"
            cid = str(chat.id).replace("-100", "")
            return f"https://t.me/c/{cid}/{msg_id}"
        except: return None

    async def _process_media(self, peer, msg_id):
        try:
            m = await self.client.get_messages(peer, ids=msg_id)
            if not m or not (m.voice or m.video_note): return
            ext = "video.mp4" if m.video_note else "voice.ogg"
            label = "Кружочек" if m.video_note else "Голосовое"

            chat = await m.get_chat()
            sender = await m.get_sender()
            s_name = utils.get_display_name(sender) if sender else "Неизвестный"

            file_bytes = io.BytesIO()
            await self.client.download_media(m, file=file_bytes)
            text = await self.transcriber.transcribe(file_bytes.getvalue(), ext)

            safe_text = html.escape(text)
            response = (
                f"<b>Чат:</b> {html.escape(getattr(chat, 'title', 'ЛС'))}\n"
                f"<b>От:</b> {html.escape(s_name)}\n"
                f"<b>Тип:</b> {label}\n"
                f"--------------------\n\n{safe_text}"
            )

            # Для длинных текстов используем простую логику (можно добавить сплиттер из пред. шага)
            await self.bot_sender.send_message(
                self.my_id, response, "🔗 Перейти к сообщению", self._get_link(chat, msg_id)
            )
        except Exception as e:
            logger.error(f"Ошибка медиа: {e}")