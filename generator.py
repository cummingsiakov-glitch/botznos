# -*- coding: utf-8 -*-
"""
Обёртка над Google Generative Language API для генерации изображений.

Ключевые моменты:
  • Промт пользователя передаётся ДОСЛОВНО (verbatim) — мы не «дописываем» и не
    искажаем его. Качество повышается только через параметры API
    (imageConfig.imageSize / aspectRatio), а не через порчу текста промта.
  • Отдаём картинку в максимальном качестве (PNG, без пережатия).
  • Встроен цикл повторов с ротацией ключей — при 429 запрос автоматически
    уходит на следующий свободный ключ.
"""

import asyncio
import base64
import re

import aiohttp

from config import API_BASE, MODEL_NAME, REQUEST_TIMEOUT
from key_rotator import KeyRotator


class GenerationError(Exception):
    """Ошибка генерации, пригодная для показа пользователю."""


def _parse_retry_after(headers, body: str) -> float | None:
    """Пытается вытащить рекомендуемую задержку из ответа 429."""
    ra = headers.get("Retry-After")
    if ra:
        try:
            return float(ra)
        except ValueError:
            pass
    # Google иногда кладёт retryDelay: "37s" в тело ошибки.
    m = re.search(r'"retryDelay"\s*:\s*"?(\d+(?:\.\d+)?)s', body)
    if m:
        return float(m.group(1))
    return None


def _extract_image(data: dict) -> tuple[bytes, str]:
    """Достаёт первое изображение (bytes + mime) из ответа generateContent."""
    candidates = data.get("candidates") or []
    for cand in candidates:
        parts = (cand.get("content") or {}).get("parts") or []
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                raw = base64.b64decode(inline["data"])
                mime = inline.get("mimeType") or inline.get("mime_type") or "image/png"
                return raw, mime
    # Картинки нет — возможно, сработал фильтр безопасности.
    fb = (candidates[0].get("finishReason") if candidates else None) or "UNKNOWN"
    raise GenerationError(f"Модель не вернула изображение (finishReason={fb}).")


async def generate_image(
    rotator: KeyRotator,
    prompt: str,
    resolution: str = "2K",
    aspect_ratio: str = "1:1",
    max_attempts: int | None = None,
) -> tuple[bytes, str]:
    """
    Генерирует изображение по промту.

    :returns: (image_bytes, mime_type)
    """
    endpoint = f"{API_BASE}/models/{MODEL_NAME}:generateContent"

    payload = {
        # Промт пользователя передаётся как есть — без изменений.
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {
                "aspectRatio": aspect_ratio,
                "imageSize": resolution,   # "1K" | "2K" | "4K" — управляет разрешением
            },
        },
    }

    attempts = max_attempts or (len(rotator._states) * 2)
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    last_err: str = "неизвестная ошибка"

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for _ in range(attempts):
            state = await rotator.acquire()
            try:
                async with session.post(
                    endpoint,
                    params={"key": state.key},
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    text = await resp.text()

                    if resp.status == 200:
                        await rotator.release_success(state)
                        return _extract_image(await _safe_json(text))

                    if resp.status == 429:
                        # Лимит: остужаем ключ и уходим на следующий.
                        retry_after = _parse_retry_after(resp.headers, text)
                        await rotator.release_rate_limited(state, retry_after)
                        last_err = "лимит запросов (429) — переключаюсь на другой ключ"
                        continue

                    if resp.status in (500, 502, 503, 504):
                        # Временная ошибка сервера — просто пробуем снова.
                        await rotator.release_error(state)
                        last_err = f"временная ошибка сервера ({resp.status})"
                        await asyncio.sleep(1.5)
                        continue

                    # 400/403 и прочее — обычно проблема ключа/запроса.
                    await rotator.release_error(state)
                    last_err = _short_api_error(text, resp.status)
                    # 403 часто означает «этот ключ невалиден» — пробуем другой.
                    if resp.status in (400, 403):
                        continue
                    raise GenerationError(last_err)

            except asyncio.TimeoutError:
                await rotator.release_error(state)
                last_err = "таймаут запроса к API"
            except aiohttp.ClientError as e:
                await rotator.release_error(state)
                last_err = f"сетевая ошибка: {e}"

    raise GenerationError(f"Не удалось сгенерировать изображение. Причина: {last_err}.")


async def _safe_json(text: str) -> dict:
    import json
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise GenerationError("Некорректный ответ API (не JSON).")


def _short_api_error(text: str, status: int) -> str:
    import json
    try:
        msg = json.loads(text).get("error", {}).get("message", "")
        if msg:
            return f"API {status}: {msg[:180]}"
    except Exception:
        pass
    return f"API вернул статус {status}."
