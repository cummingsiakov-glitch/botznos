# -*- coding: utf-8 -*-
"""
Умный ротатор API-ключей.

Цель: максимально эффективно распределять нагрузку между 10 ключами и
НИКОГДА не «упираться» в 429 (Too Many Requests / лимит).

Логика:
  • Round-robin по всем доступным ключам (равномерная нагрузка).
  • При получении 429 ключ уходит в «остывание» (cooldown). Длительность берётся
    из заголовка Retry-After, если он есть, иначе — DEFAULT_COOLDOWN_SECONDS
    с экспоненциальным ростом при повторных 429 подряд.
  • Успешный запрос сбрасывает счётчик подряд идущих ошибок ключа.
  • Если ВСЕ ключи «остывают», ротатор дожидается ближайшего освобождающегося,
    а не долбит API вслепую.
  • Приоритет отдаётся ключам, которые дольше всех «отдыхали» (меньше свежих 429).
"""

import asyncio
import time

from config import DEFAULT_COOLDOWN_SECONDS


class _KeyState:
    __slots__ = ("key", "cooldown_until", "consecutive_429", "in_flight", "success", "fail")

    def __init__(self, key: str):
        self.key = key
        self.cooldown_until = 0.0     # timestamp, до которого ключ недоступен
        self.consecutive_429 = 0      # сколько 429 подряд получил ключ
        self.in_flight = 0            # сколько активных запросов сейчас на ключе
        self.success = 0              # счётчик успехов (для статистики)
        self.fail = 0                 # счётчик ошибок (для статистики)


class KeyRotator:
    def __init__(self, keys: list[str], max_cooldown: int = 900):
        if not keys:
            raise ValueError("Список API-ключей пуст. Заполните переменную `variables`.")
        self._states = [_KeyState(k) for k in keys]
        self._rr = 0                          # указатель round-robin
        self._lock = asyncio.Lock()
        self._max_cooldown = max_cooldown     # верхний предел остывания (сек)

    # ── публичный API ──────────────────────────────────────────────────────
    async def acquire(self) -> _KeyState:
        """Возвращает наиболее подходящий доступный ключ. Ждёт, если все заняты."""
        while True:
            now = time.time()
            async with self._lock:
                available = [s for s in self._states if s.cooldown_until <= now]
                if available:
                    # Среди доступных выбираем «самый разгруженный»:
                    #  1) меньше всего активных запросов,
                    #  2) меньше всего свежих 429,
                    #  затем round-robin для равномерности.
                    available.sort(key=lambda s: (s.in_flight, s.consecutive_429))
                    min_load = (available[0].in_flight, available[0].consecutive_429)
                    tied = [s for s in available if (s.in_flight, s.consecutive_429) == min_load]
                    chosen = tied[self._rr % len(tied)]
                    self._rr += 1
                    chosen.in_flight += 1
                    return chosen

                # Все ключи остывают — считаем, сколько ждать до ближайшего.
                wait = min(s.cooldown_until for s in self._states) - now

            # Ждём вне блокировки, чтобы не морозить другие корутины.
            await asyncio.sleep(min(max(wait, 0.5), 15))

    async def release_success(self, state: _KeyState) -> None:
        async with self._lock:
            state.in_flight = max(0, state.in_flight - 1)
            state.consecutive_429 = 0
            state.success += 1

    async def release_rate_limited(self, state: _KeyState, retry_after: float | None = None) -> None:
        """Помечает ключ как словивший 429 и отправляет его в cooldown."""
        async with self._lock:
            state.in_flight = max(0, state.in_flight - 1)
            state.consecutive_429 += 1
            state.fail += 1
            if retry_after and retry_after > 0:
                cd = retry_after
            else:
                # Экспоненциальный backoff: 60, 120, 240 ... но не выше max_cooldown.
                cd = min(DEFAULT_COOLDOWN_SECONDS * (2 ** (state.consecutive_429 - 1)),
                         self._max_cooldown)
            state.cooldown_until = time.time() + cd

    async def release_error(self, state: _KeyState) -> None:
        """Прочие ошибки (не 429) — просто освобождаем слот, без cooldown."""
        async with self._lock:
            state.in_flight = max(0, state.in_flight - 1)
            state.fail += 1

    def snapshot(self) -> list[dict]:
        """Короткая статистика по ключам (для команды /keys)."""
        now = time.time()
        out = []
        for i, s in enumerate(self._states, 1):
            cooling = max(0, round(s.cooldown_until - now))
            out.append({
                "n": i,
                "tail": s.key[-4:] if len(s.key) >= 4 else s.key,
                "in_flight": s.in_flight,
                "cooldown": cooling,
                "success": s.success,
                "fail": s.fail,
            })
        return out
