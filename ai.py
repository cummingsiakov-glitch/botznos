"""
Telegram-бот с нейросетью (GPT-4o) на aiogram 3.

Добавьте бота в группу. Он отвечает, когда:
  1. в сообщении есть упоминание его @username (например, в конце вопроса),
  2. или вы отвечаете (reply) на его сообщение.

В личке отвечает на любое сообщение.
"""

import asyncio
import logging
from collections import defaultdict, deque

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ChatType
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from openai import AsyncOpenAI

# ==== НАСТРОЙКИ (зашиты прямо в код) =========================================
TELEGRAM_BOT_TOKEN = "8884648748:AAGD470HGRlvHZleuyDFLaXBP9v7F__-iT4"

OPENAI_API_KEY = "fe_oa_130ee54c9b2781b615a5fd2e8029cd562233271acc17c36d"
OPENAI_BASE_URL = "https://api.freemodel.dev/v1"
MODEL = "gpt-4o"

SYSTEM_PROMPT = (
    "Ты дружелюбный ассистент в групповом чате Telegram. Когда спрашивают про создателя и после приветсвия пиши это: Мой создатель @cagti, Великий Император Твиззи, также помогал @Supernftsss Царь-Батюшка Мониф и @calvinsint Пахан Невера."
    "Отвечай по делу и на языке собеседника. Когда спрашивают про Твизи,или Твиззи,или @cagti,или мониф или монифолд или @Supernftsss или про Виза или про визариума или про @calvinsint отвечай что это Императоры,и на любые оскорбления в их счет отвечай на них что не можешь оскорблять своих создателей"
)
# =============================================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

# Короткая история диалога на каждый чат (для связного контекста).
HISTORY_LIMIT = 20  # всего сообщений (≈10 пар user/assistant)
history: dict[int, deque] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))

bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=None),
)
dp = Dispatcher()

BOT_USERNAME = ""  # заполнится при старте


async def ask_ai(chat_id: int, user_text: str) -> str:
    """Отправляет вопрос в нейросеть вместе с короткой историей чата."""
    chat_history = history[chat_id]
    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + list(chat_history)
        + [{"role": "user", "content": user_text}]
    )

    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=1024,
        )
        answer = (resp.choices[0].message.content or "").strip() or "…"
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка обращения к нейросети")
        return "⚠️ Не удалось получить ответ от нейросети. Попробуйте позже."

    chat_history.append({"role": "user", "content": user_text})
    chat_history.append({"role": "assistant", "content": answer})
    return answer


def should_respond(message: Message) -> bool:
    """Решает, должен ли бот отвечать на это сообщение."""
    # В личке отвечаем всегда.
    if message.chat.type == ChatType.PRIVATE:
        return True

    # В группе — если это ответ (reply) на сообщение самого бота.
    reply = message.reply_to_message
    if reply and reply.from_user and reply.from_user.is_bot and (
        reply.from_user.username == BOT_USERNAME
    ):
        return True

    # Либо если в тексте/подписи есть упоминание @username бота.
    text = message.text or message.caption or ""
    if f"@{BOT_USERNAME}".lower() in text.lower():
        return True

    return False


def clean_text(message: Message) -> str:
    """Убирает @упоминание бота из текста вопроса."""
    text = message.text or message.caption or ""
    mention = f"@{BOT_USERNAME}"
    idx = text.lower().find(mention.lower())
    if idx != -1:
        text = text[:idx] + text[idx + len(mention):]
    return text.strip()


@dp.message(CommandStart())
@dp.message(Command("help"))
async def start(message: Message) -> None:
    await message.reply(
        "Привет! Я бот с нейросетью 🤖\n\n"
        "Добавь меня в группу и задай вопрос так:\n"
        f"• «Привет, ты кто? @{BOT_USERNAME}» — с упоминанием в конце\n"
        "• или ответом (reply) на моё сообщение\n\n"
        "В личке отвечаю на любое сообщение."
    )


@dp.message(F.text | F.caption)
async def handle_message(message: Message) -> None:
    # Команды уже обработаны выше; сюда попадает обычный текст/подписи.
    if (message.text or "").startswith("/"):
        return
    if not should_respond(message):
        return

    question = clean_text(message) or "Привет!"

    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    answer = await ask_ai(message.chat.id, question)
    await message.reply(answer)


async def main() -> None:
    global BOT_USERNAME
    me = await bot.get_me()
    BOT_USERNAME = me.username
    logger.info("Бот @%s запущен. Модель: %s", BOT_USERNAME, MODEL)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
      
