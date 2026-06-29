import asyncio
import logging
import time
import os
import random
from aiogram import Bot, Dispatcher, types, F, html
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaPhoto, InputMediaVideo,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.enums import PollType
from aiogram.exceptions import TelegramBadRequest

TOKEN = "8684585914:AAEL7rsodIVd1lVrVNWH8G5gYTNTBkkj-yM"
CHANNEL_ID = -1001896110175    
MOD_CHAT_ID = -1001717282111    
RULES_LINK = "https://t.me/masayodoempirerules"
COMMENTS_CHAT_ID = -1001697815994 

PUBLISH_INTERVAL = 180 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

pending_posts = {}
publish_queue = [] 
last_publish_time = 0 

moderator_stats = {}

class RegForm(StatesGroup):
    waiting_name = State()
    waiting_universe = State()
    waiting_char_universe = State()  # новое состояние для вселенной персонажа (мнение)
    waiting_players = State()
    waiting_conditions = State()
    waiting_format = State()      
    waiting_photo = State()
    waiting_photo2 = State()

# ---------- КЛАВИАТУРЫ ----------

def get_main_kb():
    """Инлайн-клавиатура для выбора типа регистрации с цветными кнопками"""
    buttons = [
        [
            InlineKeyboardButton(text="📝 Мнение ", callback_data="reg_opinion", style="primary"),
            InlineKeyboardButton(text="⚔️ ПБ ⚔️", callback_data="reg_pb", style="primary")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_confirm_kb():
    """Инлайн-клавиатура подтверждения с цветными кнопками"""
    buttons = [
        [InlineKeyboardButton(text="На модерацию ✅", callback_data="confirm_send", style="success")],
        [InlineKeyboardButton(text="Отмена ❌", callback_data="cancel", style="danger")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_restart_kb():
    """Reply-клавиатура с кнопкой перезапуска (всегда видна внизу)"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🤖 Перезапустить")]],
        resize_keyboard=True
    )

# ---------- ОСНОВНОЕ МЕНЮ ----------

async def show_main_menu(message: types.Message, state: FSMContext):
    """Показывает главное меню: инлайн-выбор + reply-кнопка перезапуска"""
    await state.clear()
    await message.answer(
        "Салам, статюганище! Выбери тип регистрации:",
        reply_markup=get_main_kb()
    )
    await message.answer(
        "Для перезапуска бота нажмите кнопку ниже:",
        reply_markup=get_restart_kb()
    )

# ---------- РАБОТА ПУБЛИКАЦИИ ----------

async def publication_worker():
    global last_publish_time
    while True:
        current_time = time.time()
        if publish_queue and (current_time - last_publish_time >= PUBLISH_INTERVAL):
            data = publish_queue.pop(0)
            try:
                sent_msg = None
                
                if data['reg_type'] == 'reg_opinion':
                    if data['type1'] == 'photo':
                        sent_msg = await bot.send_photo(CHANNEL_ID, data['photo1'], caption=data['final_caption'], parse_mode="HTML")
                    else:
                        sent_msg = await bot.send_video(CHANNEL_ID, data['photo1'], caption=data['final_caption'], parse_mode="HTML")
                else:
                    m1 = InputMediaPhoto(media=data['photo1'], caption=data['final_caption'], parse_mode="HTML") if data['type1'] == 'photo' else InputMediaVideo(media=data['photo1'], caption=data['final_caption'], parse_mode="HTML")
                    m2 = InputMediaPhoto(media=data['photo2']) if data['type2'] == 'photo' else InputMediaVideo(media=data['photo2'])
                    
                    media_group = await bot.send_media_group(CHANNEL_ID, media=[m1, m2])
                    sent_msg = media_group[0]
                
                last_publish_time = time.time()
                logging.info("Пост успешно опубликован.")

                if data['reg_type'] == 'reg_pb' and sent_msg:
                    message_id = sent_msg.message_id
                    
                    players_raw = data.get('players', '').split('\n')
                    names_raw = data.get('name', '').split('\n')
                    conditions = data.get('conditions', 'Нет условий')
                    
                    clean_players = [p.strip() for p in players_raw if p.strip()]
                    clean_names = [n.strip() for n in names_raw if n.strip()]
                    
                    walker_idx = random.randint(0, len(clean_players) - 1) if clean_players else 0
                    walker_user = clean_players[walker_idx] if clean_players else "@unknown"
                    walker_char = clean_names[walker_idx] if walker_idx < len(clean_names) else "Персонаж"
                    
                    poll_options = []
                    for name in clean_names:
                        if name:
                            poll_options.append(name)
                    
                    if not poll_options:
                        poll_options = ["Player 1", "Player 2"]

                    try:
                        await bot.send_poll(
                            chat_id=CHANNEL_ID,
                            question="Кто победит?",
                            options=poll_options,
                            is_anonymous=True,
                            type=PollType.REGULAR,
                            reply_to_message_id=message_id 
                        )
                    except Exception as e:
                        logging.error(f"Ошибка создания опроса: {e}")

                    channel_id_clean = str(CHANNEL_ID)[4:]
                    post_link = f"https://t.me/c/{channel_id_clean}/{message_id}"

                    comment_text = (
                        f" <a href='{post_link}'>Пост ПБ</a>\n\n"
                        f"<b>Бот определил, ходит — {walker_user}. Удачи в пруфбаттле! 🔥</b>\n\n"
                        f"<b>Условие пруфбаттла: {conditions}</b>"
                    )
                    
                    kb_comment = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="👉 Перейти к посту", url=post_link, style="primary")
                    ]])

                    try:
                        await bot.send_message(
                            chat_id=COMMENTS_CHAT_ID,
                            text=comment_text,
                            parse_mode="HTML",
                            reply_markup=kb_comment,
                            disable_web_page_preview=False
                        )
                    except Exception as e:
                        logging.error(f"Ошибка отправки комментария: {e}")

            except Exception as e:
                logging.error(f"Ошибка публикации: {e}")
        await asyncio.sleep(10)

# ---------- ХЕНДЛЕРЫ КОМАНД ----------

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await show_main_menu(message, state)

@dp.message(Command("reyt"))
async def show_rating(message: types.Message):
    if not moderator_stats:
        await message.answer("Пока нет статистики.")
        return
    
    sorted_stats = sorted(moderator_stats.items(), key=lambda x: x[1], reverse=True)
    text = "<b>Рейтинг модераторов:</b>\n\n"
    for i, (user_id, count) in enumerate(sorted_stats, 1):
        text += f"{i}. <a href='tg://user?id={user_id}'>Модератор</a> — {count}\n"
    
    await message.answer(text, parse_mode="HTML")

# ---------- ОБРАБОТКА REPLY-КНОПКИ ПЕРЕЗАПУСКА ----------

@dp.message(F.text == "🤖 Перезапустить")
async def restart_handler(message: types.Message, state: FSMContext):
    await show_main_menu(message, state)

# ---------- ОБРАБОТКА ИНЛАЙН-КНОПОК ВЫБОРА ТИПА ----------

@dp.callback_query(F.data.in_(["reg_opinion", "reg_pb"]))
async def start_reg(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(reg_type=callback.data)
    await state.set_state(RegForm.waiting_name)
    if callback.data == "reg_opinion":
        text = "<b>Отправь имя персонажа..</b>"
    else:
        text = "<b>Отправь имена персонажей (с новой строки)..</b>"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

# ---------- ЭТАПЫ РЕГИСТРАЦИИ ----------

@dp.message(RegForm.waiting_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(RegForm.waiting_universe)
    data = await state.get_data()
    if data['reg_type'] == 'reg_opinion':
        text = "<b>Отправь вселенные или персонажей которые он аннигилирует (каждого с новой строки или через запятую)..</b>"
    else:
        text = "<b>Отправь вселенные (каждую с новой строки или через запятую)..</b>"
    await message.answer(text, parse_mode="HTML")

@dp.message(RegForm.waiting_universe)
async def process_universe(message: types.Message, state: FSMContext):
    await state.update_data(universe=message.text)
    data = await state.get_data()
    if data['reg_type'] == 'reg_pb':
        await state.set_state(RegForm.waiting_players)
        text = "<b>Отправь юзернеймы игроков (каждый с новой строки)..</b>"
        await message.answer(text, parse_mode="HTML")
    else:
        # для мнения — запрашиваем вселенную персонажа отдельно
        await state.set_state(RegForm.waiting_char_universe)
        text = "<b>Из какой вселенной персонаж?</b>"
        await message.answer(text, parse_mode="HTML")

@dp.message(RegForm.waiting_char_universe)
async def process_char_universe(message: types.Message, state: FSMContext):
    await state.update_data(char_universe=message.text)
    await state.set_state(RegForm.waiting_conditions)
    text = "<b>Отправь условия (или напиши 'нет')..</b>"
    await message.answer(text, parse_mode="HTML")

@dp.message(RegForm.waiting_players)
async def process_players(message: types.Message, state: FSMContext):
    await state.update_data(players=message.text)
    await state.set_state(RegForm.waiting_conditions)
    text = "<b>Отправь условия (или напиши 'нет')..</b>"
    await message.answer(text, parse_mode="HTML")

@dp.message(RegForm.waiting_conditions)
async def process_cond(message: types.Message, state: FSMContext):
    await state.update_data(conditions=message.text)
    data = await state.get_data()
    if data['reg_type'] == 'reg_pb':
        await state.set_state(RegForm.waiting_photo)
        text = "<b>Отправь арт или видео (эдит)..</b>"
        await message.answer(text, parse_mode="HTML")
    else:
        # Для мнений спрашиваем формат
        await state.set_state(RegForm.waiting_format)
        text = "<b>Отправь формат (например: ПБ, ГЧ) или напиши 'нет'..</b>"
        await message.answer(text, parse_mode="HTML")

@dp.message(RegForm.waiting_format)
async def process_format(message: types.Message, state: FSMContext):
    await state.update_data(format=message.text)
    await state.set_state(RegForm.waiting_photo)
    text = "<b>Отправь арт или видео (эдит)..</b>"
    await message.answer(text, parse_mode="HTML")

@dp.message(RegForm.waiting_photo, F.photo | F.video)
async def process_photo1(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    await state.update_data(photo1=file_id, type1='photo' if message.photo else 'video')
    data = await state.get_data()
    if data['reg_type'] == 'reg_pb':
        await state.set_state(RegForm.waiting_photo2)
        text = "<b>Отправь второй арт или видео..</b>"
        await message.answer(text, parse_mode="HTML")
    else:
        await finalize_preview(message, state)

@dp.message(RegForm.waiting_photo2, F.photo | F.video)
async def process_photo2(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    await state.update_data(photo2=file_id, type2='photo' if message.photo else 'video')
    await finalize_preview(message, state)

async def finalize_preview(message, state):
    data = await state.get_data()
    
    if data['reg_type'] == 'reg_opinion':
        # Авторство
        if message.from_user.username:
            author_text = f"@{html.quote(message.from_user.username)}"
        else:
            author_text = f'<a href="tg://user?id={message.from_user.id}">{html.quote(message.from_user.first_name)}</a>'
        author_str = f"© Позиция ➥ {author_text}"
        
        # Персонаж
        char_name = html.quote(data['name'])
        
        # Вселенные (список для уничтожения)
        all_verses = [u.strip() for u in data['universe'].replace(',', '\n').split('\n') if u.strip()]
        # Вселенная персонажа – берём из нового поля
        char_universe = data.get('char_universe', 'Неизвестная вселенная')
        first_verse_q = html.quote(char_universe)
        
        header = f"✎ {char_name} из Вселенной «{first_verse_q}» уничтожает всех нижеперечисленных"
        
        # Список вселенных/персонажей для уничтожения
        verses_list = "\n".join([f"➣ {html.quote(v)}" for v in all_verses])
        
        # Условия
        conds_text = "Нет условий" if data['conditions'].lower() == "нет" else html.quote(data['conditions'])
        
        # Формат
        raw_format = data.get('format', '')
        if raw_format.lower() == "нет" or not raw_format.strip():
            format_text = "Не указан"
        else:
            format_text = html.quote(raw_format)
        
        caption = (
            f"<b>👤 Персональное мнение ⤵</b>\n"
            f"<b>{author_str}</b>\n"
            f"<b>{header}</b>\n\n"
            f"<blockquote><b>{verses_list}</b></blockquote>\n\n"
            f"<b>┎Формат ➲ {format_text}</b>\n"
            f"<b>┖Условия ➲ {conds_text}</b>"
        )
        
        await state.update_data(final_caption=caption)
        
        target = bot.send_photo if data['type1'] == 'photo' else bot.send_video
        await target(message.chat.id, data['photo1'], caption=caption, parse_mode="HTML", reply_markup=get_confirm_kb())
        
    else:  # reg_pb
        chars = [html.quote(c.strip()) for c in data['name'].split('\n')]
        players = [html.quote(p.strip()) for p in data['players'].split('\n')]
        
        p1, p2 = (chars[0] if len(chars)>0 else "Персонаж 1"), (chars[1] if len(chars)>1 else "Персонаж 2")
        pl1, pl2 = (players[0] if len(players)>0 else "@user1"), (players[1] if len(players)>1 else "@user2")
        
        conds_text = "Нет условий" if data['conditions'].lower() == "нет" else html.quote(data['conditions'])
        
        caption = (
            f"⚔️ 𝙿𝙴𝚁𝚂𝙾𝙽𝙰𝙻 𝙿𝚁𝙾𝙾𝙵 𝙱𝙰𝚃𝚃𝙻𝙴 ⚔️\n\n"
            f"         🎮 𝙿𝚕𝚊𝚢𝚎𝚛 #𝟷 🎮\n\n"
            f"{p1} // {pl1}\n\n"
            f"                     𝚅𝚂    \n\n"
            f"         🎮 𝙿𝚕𝚊𝚢𝚎𝚛 #𝟸 🎮\n\n"
            f"{p2} // {pl2}\n\n"
            f"📖 𝚁𝚞𝚕𝚎𝚜 𝚏𝚘𝚛 𝚙𝚛𝚘𝚘𝚏𝚋𝚊𝚝𝚝𝚕𝚎: <a href='{RULES_LINK}'>ссылка на правила</a>\n\n"
            f"📋 𝙵𝚒𝚡𝚎𝚜: {conds_text}\n\n"
            f"🍀 𝙶𝚘𝚘𝚍 𝚕𝚞𝚌𝚔 𝚠𝚒𝚝𝚑 𝚝𝚑𝚎 𝚙𝚛𝚘𝚘𝚏 𝚋𝚊𝚝𝚝𝚕𝚎"
        )
        
        await state.update_data(final_caption=caption)
        
        m1 = InputMediaPhoto(media=data['photo1'], caption=caption, parse_mode="HTML") if data['type1'] == 'photo' else InputMediaVideo(media=data['photo1'], caption=caption, parse_mode="HTML")
        m2 = InputMediaPhoto(media=data['photo2']) if data['type2'] == 'photo' else InputMediaVideo(media=data['photo2'])
        await bot.send_media_group(message.chat.id, media=[m1, m2])
        await message.answer("Проверь ПБ выше. На модерацию?", reply_markup=get_confirm_kb())

# ---------- ОТПРАВКА НА МОДЕРАЦИЮ ----------

@dp.callback_query(F.data == "confirm_send")
async def send_to_mod(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_id = f"post_{callback.from_user.id}_{int(time.time())}"
    pending_posts[post_id] = data

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Опубликовать ✅", callback_data=f"publish_{post_id}", style="success"),
        InlineKeyboardButton(text="Отменить ❌", callback_data=f"reject_{post_id}", style="danger")
    ]])
    
    if data['reg_type'] == 'reg_opinion':
        target = bot.send_photo if data['type1'] == 'photo' else bot.send_video
        await target(MOD_CHAT_ID, data['photo1'], caption=data['final_caption'], parse_mode="HTML", reply_markup=kb)
    else:
        m1 = InputMediaPhoto(media=data['photo1'], caption=data['final_caption'], parse_mode="HTML") if data['type1'] == 'photo' else InputMediaVideo(media=data['photo1'], caption=data['final_caption'], parse_mode="HTML")
        m2 = InputMediaPhoto(media=data['photo2']) if data['type2'] == 'photo' else InputMediaVideo(media=data['photo2'])
        await bot.send_media_group(MOD_CHAT_ID, media=[m1, m2])
        await bot.send_message(MOD_CHAT_ID, f" ПБ от {callback.from_user.first_name}", reply_markup=kb)
        
    await callback.message.answer("✅ Отправлено модераторам!")
    await state.clear()

@dp.callback_query(F.data.startswith("reject_"))
async def reject_item(callback: types.CallbackQuery):
    post_id = callback.data.replace("reject_", "")
    if post_id in pending_posts:
        del pending_posts[post_id]
    await callback.message.delete()
    await bot.send_message(MOD_CHAT_ID, "⛔ Публикация отменена.")
    await callback.answer("Отменено")

@dp.callback_query(F.data.startswith("publish_"))
async def publish_item(callback: types.CallbackQuery):
    post_id = callback.data.replace("publish_", "")
    data = pending_posts.get(post_id)
    if not data:
        await callback.answer("Ошибка: пост уже в очереди!", show_alert=True)
        try: await callback.message.delete()
        except: pass
        return

    publish_queue.append(data)
    moderator_stats[callback.from_user.id] = moderator_stats.get(callback.from_user.id, 0) + 1
    
    try:
        await callback.message.delete()
        text = f"⏳ Пост от {callback.from_user.first_name} в очереди (3 мин)."
        await bot.send_message(MOD_CHAT_ID, text)
    except TelegramBadRequest:
        pass

    del pending_posts[post_id]
    await callback.answer("✅ Добавлено в очередь!")

@dp.callback_query(F.data == "cancel")
async def cancel_reg(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("❌ Отменено.")

# ---------- ЗАПУСК ----------

async def main():
    print(">>> БОТ ЗАПУЩЕН <<<")
    asyncio.create_task(publication_worker())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
