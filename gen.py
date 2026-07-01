# -*- coding: utf-8 -*-
"""
🍌 Nano-Banana Image Bot
Telegram-бот на aiogram 3.x для генерации изображений моделью nano-banana-2-lite
(Google AI Studio) с умной ротацией API-ключей и максимальным качеством вывода.
"""

import asyncio
import io
import logging
import time

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import (
    BOT_TOKEN,
    DEFAULT_ASPECT_RATIO,
    DEFAULT_RESOLUTION,
    MODEL_NAME,
    load_api_keys,
)
from generator import GenerationError, generate_image
from key_rotator import KeyRotator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("nano-banana-bot")

# ─────────────────────────────────────────────────────────────────────────────
#  Глобальное состояние
# ─────────────────────────────────────────────────────────────────────────────
rotator = KeyRotator(load_api_keys())
router = Router()

# Настройки на пользователя (в памяти). Ключ — user_id.
user_settings: dict[int, dict] = {}
# Последний промт пользователя — для кнопки «Повторить».
user_last_prompt: dict[int, str] = {}

RESOLUTIONS = ["1K", "2K", "4K"]
ASPECTS = ["1:1", "16:9", "9:16", "4:3", "3:4", "21:9"]


def get_settings(user_id: int) -> dict:
    return user_settings.setdefault(
        user_id,
        {"resolution": DEFAULT_RESOLUTION, "aspect": DEFAULT_ASPECT_RATIO, "as_file": True},
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Клавиатуры (inline)
# ─────────────────────────────────────────────────────────────────────────────
def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 Сгенерировать", callback_data="how")],
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"),
            InlineKeyboardButton(text="📊 Ключи", callback_data="keys"),
        ],
        [
            InlineKeyboardButton(text="ℹ️ О боте", callback_data="about"),
            InlineKeyboardButton(text="❓ Помощь", callback_data="help"),
        ],
    ])


def kb_settings(user_id: int) -> InlineKeyboardMarkup:
    s = get_settings(user_id)
    res_row = [
        InlineKeyboardButton(
            text=("✅ " if s["resolution"] == r else "") + r,
            callback_data=f"set_res:{r}",
        )
        for r in RESOLUTIONS
    ]
    asp_row1 = [
        InlineKeyboardButton(
            text=("✅ " if s["aspect"] == a else "") + a,
            callback_data=f"set_asp:{a}",
        )
        for a in ASPECTS[:3]
    ]
    asp_row2 = [
        InlineKeyboardButton(
            text=("✅ " if s["aspect"] == a else "") + a,
            callback_data=f"set_asp:{a}",
        )
        for a in ASPECTS[3:]
    ]
    file_btn = InlineKeyboardButton(
        text=("📄 Файл (макс. качество) ✅" if s["as_file"] else "📄 Файл (макс. качество)"),
        callback_data="toggle_file",
    )
    photo_btn = InlineKeyboardButton(
        text=("🖼 Фото (превью) ✅" if not s["as_file"] else "🖼 Фото (превью)"),
        callback_data="toggle_file",
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="— Разрешение —", callback_data="noop")],
        res_row,
        [InlineKeyboardButton(text="— Соотношение сторон —", callback_data="noop")],
        asp_row1,
        asp_row2,
        [InlineKeyboardButton(text="— Формат отправки —", callback_data="noop")],
        [file_btn, photo_btn],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="home")],
    ])


def kb_after_generation() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔁 Ещё раз", callback_data="regen"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"),
        ],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="home")],
    ])


def kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В меню", callback_data="home")],
    ])


# ─────────────────────────────────────────────────────────────────────────────
#  Тексты
# ─────────────────────────────────────────────────────────────────────────────
def welcome_text(name: str) -> str:
    return (
        f"🍌✨ <b>Nano-Banana Studio</b>\n"
        f"Привет, <b>{name}</b>!\n\n"
        f"Я генерирую изображения нейросетью <code>{MODEL_NAME}</code> "
        f"в максимальном качестве.\n\n"
        f"<b>Как пользоваться:</b>\n"
        f"Просто отправь мне текстовое описание того, что хочешь увидеть — "
        f"и через мгновение получишь картинку 🎨\n\n"
        f"<i>Твой промт я передаю модели дословно и ничего в нём не меняю.</i>"
    )


ABOUT_TEXT = (
    "ℹ️ <b>О боте</b>\n\n"
    f"• <b>Модель:</b> <code>{MODEL_NAME}</code> (Google AI Studio)\n"
    "• <b>Framework:</b> aiogram 3.x\n"
    "• <b>Качество:</b> до 4K, отправка файлом без пережатия\n"
    "• <b>Надёжность:</b> умная ротация 10 API-ключей с защитой от лимитов (429)\n\n"
    "Промт пользователя не изменяется — качество достигается параметрами API."
)

HELP_TEXT = (
    "❓ <b>Помощь</b>\n\n"
    "<b>Команды:</b>\n"
    "/start — главное меню\n"
    "/settings — настройки качества и формата\n"
    "/keys — статус API-ключей\n"
    "/help — эта справка\n\n"
    "<b>Генерация:</b>\n"
    "Отправь текст-описание — получишь картинку.\n\n"
    "<b>Советы по промту:</b>\n"
    "• Пиши конкретно: объект, стиль, освещение, ракурс.\n"
    "• Для фотореализма добавь «photorealistic, 8k, detailed».\n"
    "• Для арта укажи стиль: «oil painting», «anime», «3D render».\n"
    "• Выбирай формат «Файл», чтобы получить максимальное качество без сжатия."
)


# ─────────────────────────────────────────────────────────────────────────────
#  Хендлеры команд
# ─────────────────────────────────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(welcome_text(message.from_user.first_name), reply_markup=kb_main())


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    await message.answer(settings_text(message.from_user.id),
                         reply_markup=kb_settings(message.from_user.id))


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, reply_markup=kb_back())


@router.message(Command("keys"))
async def cmd_keys(message: Message):
    await message.answer(keys_text(), reply_markup=kb_back())


def settings_text(user_id: int) -> str:
    s = get_settings(user_id)
    fmt = "📄 Файл (макс. качество)" if s["as_file"] else "🖼 Фото (превью)"
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"• Разрешение: <b>{s['resolution']}</b>\n"
        f"• Соотношение сторон: <b>{s['aspect']}</b>\n"
        f"• Формат отправки: <b>{fmt}</b>\n\n"
        "Меняй параметры кнопками ниже 👇"
    )


def keys_text() -> str:
    snap = rotator.snapshot()
    lines = ["📊 <b>Статус API-ключей</b>\n"]
    for k in snap:
        status = "🟢 готов" if k["cooldown"] == 0 else f"🟡 остывает {k['cooldown']}с"
        lines.append(
            f"#{k['n']:>2} ••••{k['tail']} | {status} | "
            f"✅{k['success']} ❌{k['fail']} | активных: {k['in_flight']}"
        )
    ready = sum(1 for k in snap if k["cooldown"] == 0)
    lines.append(f"\n<b>Доступно сейчас:</b> {ready}/{len(snap)}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Генерация по текстовому сообщению
# ─────────────────────────────────────────────────────────────────────────────
@router.message(F.text & ~F.text.startswith("/"))
async def on_prompt(message: Message):
    prompt = message.text.strip()
    if not prompt:
        await message.answer("✏️ Пришли текстовое описание картинки.")
        return
    user_last_prompt[message.from_user.id] = prompt
    await run_generation(message, prompt, message.from_user.id)


async def run_generation(message: Message, prompt: str, user_id: int):
    s = get_settings(user_id)
    status = await message.answer(
        f"🎨 <b>Генерирую...</b>\n"
        f"<code>{_escape(prompt[:120])}</code>\n\n"
        f"📐 {s['aspect']} · 🖼 {s['resolution']} · модель <code>{MODEL_NAME}</code>\n"
        f"⏳ Подбираю свободный ключ и рисую..."
    )

    action = ChatAction.UPLOAD_DOCUMENT if s["as_file"] else ChatAction.UPLOAD_PHOTO
    started = time.time()
    try:
        # Периодически шлём "typing/uploading", пока идёт генерация.
        async def keep_alive():
            while True:
                await message.bot.send_chat_action(message.chat.id, action)
                await asyncio.sleep(4)

        ka = asyncio.create_task(keep_alive())
        try:
            image_bytes, mime = await generate_image(
                rotator, prompt,
                resolution=s["resolution"],
                aspect_ratio=s["aspect"],
            )
        finally:
            ka.cancel()

        elapsed = time.time() - started
        caption = (
            f"✅ <b>Готово!</b> за {elapsed:.1f}с\n"
            f"<code>{_escape(prompt[:200])}</code>\n"
            f"📐 {s['aspect']} · 🖼 {s['resolution']}"
        )

        ext = "png" if "png" in mime else ("jpg" if "jpeg" in mime else "img")
        fname = f"nano_banana_{int(started)}.{ext}"

        if s["as_file"]:
            # Файлом — без пережатия, максимальное качество.
            await message.answer_document(
                BufferedInputFile(image_bytes, filename=fname),
                caption=caption,
                reply_markup=kb_after_generation(),
            )
        else:
            await message.answer_photo(
                BufferedInputFile(image_bytes, filename=fname),
                caption=caption,
                reply_markup=kb_after_generation(),
            )
        await status.delete()

    except GenerationError as e:
        await status.edit_text(
            f"❌ <b>Не получилось сгенерировать</b>\n\n{_escape(str(e))}\n\n"
            f"Попробуй ещё раз или измени промт.",
            reply_markup=kb_after_generation(),
        )
    except Exception as e:  # noqa: BLE001
        log.exception("Unexpected error")
        await status.edit_text(
            f"⚠️ <b>Внутренняя ошибка:</b> {_escape(str(e))}",
            reply_markup=kb_back(),
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Callback-хендлеры (inline-кнопки)
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data == "home")
async def cb_home(call: CallbackQuery):
    await call.message.edit_text(welcome_text(call.from_user.first_name), reply_markup=kb_main())
    await call.answer()


@router.callback_query(F.data == "how")
async def cb_how(call: CallbackQuery):
    await call.message.edit_text(
        "🎨 <b>Генерация</b>\n\n"
        "Просто отправь мне текстовое описание картинки одним сообщением.\n\n"
        "Например:\n"
        "<i>«портрет рыжего кота-космонавта в шлеме, неон, киберпанк, 8k»</i>",
        reply_markup=kb_back(),
    )
    await call.answer()


@router.callback_query(F.data == "about")
async def cb_about(call: CallbackQuery):
    await call.message.edit_text(ABOUT_TEXT, reply_markup=kb_back())
    await call.answer()


@router.callback_query(F.data == "help")
async def cb_help(call: CallbackQuery):
    await call.message.edit_text(HELP_TEXT, reply_markup=kb_back())
    await call.answer()


@router.callback_query(F.data == "keys")
async def cb_keys(call: CallbackQuery):
    await call.message.edit_text(keys_text(), reply_markup=kb_back())
    await call.answer("Обновлено")


@router.callback_query(F.data == "settings")
async def cb_settings(call: CallbackQuery):
    await call.message.edit_text(settings_text(call.from_user.id),
                                 reply_markup=kb_settings(call.from_user.id))
    await call.answer()


@router.callback_query(F.data.startswith("set_res:"))
async def cb_set_res(call: CallbackQuery):
    res = call.data.split(":", 1)[1]
    get_settings(call.from_user.id)["resolution"] = res
    await call.message.edit_reply_markup(reply_markup=kb_settings(call.from_user.id))
    await call.answer(f"Разрешение: {res}")


@router.callback_query(F.data.startswith("set_asp:"))
async def cb_set_asp(call: CallbackQuery):
    asp = call.data.split(":", 1)[1]
    get_settings(call.from_user.id)["aspect"] = asp
    await call.message.edit_reply_markup(reply_markup=kb_settings(call.from_user.id))
    await call.answer(f"Соотношение: {asp}")


@router.callback_query(F.data == "toggle_file")
async def cb_toggle_file(call: CallbackQuery):
    s = get_settings(call.from_user.id)
    s["as_file"] = not s["as_file"]
    await call.message.edit_text(settings_text(call.from_user.id),
                                 reply_markup=kb_settings(call.from_user.id))
    await call.answer("Формат изменён")


@router.callback_query(F.data == "regen")
async def cb_regen(call: CallbackQuery):
    prompt = user_last_prompt.get(call.from_user.id)
    await call.answer()
    if not prompt:
        await call.message.answer("Сначала пришли текстовое описание 🙂")
        return
    await run_generation(call.message, prompt, call.from_user.id)


# ─────────────────────────────────────────────────────────────────────────────
#  Утилиты
# ─────────────────────────────────────────────────────────────────────────────
def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ─────────────────────────────────────────────────────────────────────────────
#  Запуск
# ─────────────────────────────────────────────────────────────────────────────
async def main():
    if BOT_TOKEN.startswith("PASTE_"):
        raise SystemExit("⛔ Укажите BOT_TOKEN в config.py")

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    log.info("Бот запущен. Ключей загружено: %d", len(load_api_keys()))
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
