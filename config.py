# -*- coding: utf-8 -*-
"""
Конфигурация бота.

ВАЖНО:
  • Все API-ключи от Google AI Studio хранятся в ОДНОЙ переменной `variables`
    и перечисляются через запятую (у вас их будет 10).
  • Токен Telegram-бота задаётся прямо в коде (в отдельной переменной `BOT_TOKEN`),
    как вы и просили — без отдельной переменной-контейнера.
"""

# ─────────────────────────────────────────────────────────────────────────────
#  API-КЛЮЧИ GOOGLE AI STUDIO  (все 10 ключей — в одну строку, через запятую)
# ─────────────────────────────────────────────────────────────────────────────
variables = "AIzaSyC6OTB4tGiOpxrhV-2FPhaF5wtCzwPLXio,AIzaSyCzFUdWh-s_Bk5yuYV441kjSmq6x99ZA14,AIzaSyASQeZyO5V0aG7ZM1KOC6mxSxUV3ut325Q,AIzaSyD_-xoOr8zwZVV58rxC3_dmO23tlIOLCyo,AIzaSyCuyXxLwvNfSbi0OAPoY27efAbkxJaB47I,AIzaSyDtlTw6z9runckcsN5Sz-OSR5NhjZJTbmo,AIzaSyBCW9I5tw8VdcbOt_IbEXCNwlJD6flp0OQ,AIzaSyCWwAn_158UixzxFqhrBjvSspK5yy5zrCk,AIzaSyD_2aRIyFre0jO5eaIJN65IdCBwi9827xs,AIzaSyAzJjn5OnLWjAJO5_kBSPMGoR0ugZ3MEXE"

# ─────────────────────────────────────────────────────────────────────────────
#  ТОКЕН TELEGRAM-БОТА  (вставьте токен от @BotFather прямо сюда)
# ─────────────────────────────────────────────────────────────────────────────
BOT_TOKEN = "8883702079:AAGMrsgXfYKQHVKeLJZOm0F3lYpoAvljiWU"

# ─────────────────────────────────────────────────────────────────────────────
#  МОДЕЛЬ ГЕНЕРАЦИИ ИЗОБРАЖЕНИЙ
# ─────────────────────────────────────────────────────────────────────────────
# Идентификатор модели в Google Generative Language API.
MODEL_NAME = "imagen-3.0-generate-002"

# Базовый эндпоинт Google Generative Language API.
API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# ─────────────────────────────────────────────────────────────────────────────
#  ПАРАМЕТРЫ КАЧЕСТВА / РОТАЦИИ
# ─────────────────────────────────────────────────────────────────────────────
# Разрешение по умолчанию: "1K" | "2K" | "4K". Для максимального качества — "4K".
DEFAULT_RESOLUTION = "2K"

# Соотношение сторон по умолчанию.
DEFAULT_ASPECT_RATIO = "1:1"

# Сколько секунд «остужать» ключ по умолчанию при получении 429 без Retry-After.
DEFAULT_COOLDOWN_SECONDS = 60

# Таймаут HTTP-запроса к API (сек).
REQUEST_TIMEOUT = 180


def load_api_keys() -> list[str]:
    """Разбирает переменную `variables` в список ключей, убирая пробелы и пустые."""
    return [k.strip() for k in variables.split(",") if k.strip()]
