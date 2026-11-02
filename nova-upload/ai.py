# -*- coding: utf-8 -*-
"""طبقة الذكاء الاصطناعي — بثّ حي (Streaming) + مزوّد مجاني بدون مفتاح"""

import asyncio
import json
import time
import urllib.parse
from typing import AsyncIterator

import requests

import config


class AIError(Exception):
    """خطأ عام"""


class BusyError(AIError):
    """الخدمة مزدحمة — اطلب من المستخدم المحاولة لاحقاً"""


# ================= حالة الوضع المجاني =================
_lock = asyncio.Lock()
_last_call = 0.0
MAX_WAIT = 60


def is_keyed() -> bool:
    return bool(config.AI_KEY and config.AI_BASE and config.AI_MODELS)


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if is_keyed():
        h["Authorization"] = f"Bearer {config.AI_KEY}"
        if "openrouter" in config.AI_BASE:
            h["HTTP-Referer"] = "https://t.me/"
            h["X-Title"] = config.BOT_NAME
    return h


def _endpoint() -> str:
    base = config.AI_BASE if is_keyed() else config.KEYLESS["base"]
    return base.rstrip("/") + "/chat/completions" if is_keyed() else base


def _models():
    return config.AI_MODELS if is_keyed() else config.KEYLESS["models"]


def _payload(model: str, messages: list, stream: bool) -> dict:
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": config.AI_MAX_TOKENS,
        "temperature": config.AI_TEMPERATURE,
        "stream": stream,
    }
    # Gemini: تعطيل التفكير العميق لردود فورية
    if is_keyed() and "generativelanguage" in config.AI_BASE:
        body["reasoning_effort"] = "none"
    return body


def supports_stream() -> bool:
    """بثّ Gemini عبر OpenAI-compat غير مستقر — نستخدم الرد المباشر"""
    return not (is_keyed() and "generativelanguage" in config.AI_BASE)


def _build(system_prompt: str, history: list, user_text: str):
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})
    return messages


# ================= البثّ =================
def _stream_worker(messages, queue, loop):
    url = _endpoint()
    headers = _headers()
    last = None
    for model in _models():
        try:
            with requests.post(
                url, headers=headers,
                json=_payload(model, messages, True),
                stream=True, timeout=config.AI_TIMEOUT,
            ) as r:
                if r.status_code == 402:
                    raise BusyError("rate limited")
                if r.status_code >= 400:
                    raise AIError(f"{r.status_code}: {r.text[:160]}")

                ctype = (r.headers.get("content-type") or "").lower()
                got_any = False

                if "event-stream" in ctype:
                    for raw in r.iter_lines(decode_unicode=True):
                        if not raw or not raw.startswith("data:"):
                            continue
                        chunk = raw[5:].strip()
                        if chunk == "[DONE]":
                            break
                        try:
                            data = json.loads(chunk)
                            delta = data["choices"][0]["delta"]
                            piece = delta.get("content") or ""
                        except Exception:
                            continue
                        if piece:
                            got_any = True
                            loop.call_soon_threadsafe(queue.put_nowait, piece)
                else:
                    data = r.json()
                    text = data["choices"][0]["message"]["content"] or ""
                    if text:
                        got_any = True
                        loop.call_soon_threadsafe(queue.put_nowait, text)

                if not got_any:
                    raise AIError("رد فارغ")
                loop.call_soon_threadsafe(queue.put_nowait, None)
                return
        except BusyError as e:
            loop.call_soon_threadsafe(queue.put_nowait, e)
            return
        except Exception as e:
            last = e
            continue
    loop.call_soon_threadsafe(queue.put_nowait, last or AIError("لا يوجد موديل"))


async def _plain_call(messages: list) -> str:
    url = _endpoint()
    headers = _headers()
    last = None
    for model in _models():
        for attempt in range(2):          # محاولة إضافية عند انقطاع عابر
            try:
                r = requests.post(url, headers=headers,
                                  json=_payload(model, messages, False),
                                  timeout=config.AI_TIMEOUT)
                if r.status_code in (402, 429):
                    raise BusyError("rate limited")
                if r.status_code >= 500 and attempt == 0:
                    raise AIError(f"{r.status_code}")
                if r.status_code >= 400:
                    raise AIError(f"{r.status_code}: {r.text[:160]}")
                text = (r.json()["choices"][0]["message"]["content"] or "").strip()
                if text:
                    return text
                raise AIError("رد فارغ")
            except BusyError:
                raise
            except Exception as e:
                last = e
    raise AIError(str(last) if last else "لا يوجد موديل")


async def _guard(coro_factory):
    """ينفّذ الطلب داخل الطابور المجاني إن لم يوجد مفتاح"""
    global _last_call
    if is_keyed():
        return await coro_factory()

    gap = float(config.KEYLESS.get("min_gap", 45))
    async with _lock:
        wait = gap - (time.monotonic() - _last_call)
        if wait > MAX_WAIT:
            raise BusyError("queue full")
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            return await coro_factory()
        finally:
            _last_call = time.monotonic()


async def stream(system_prompt: str, history: list, user_text: str) -> AsyncIterator[str]:
    """يرجع الرد على شكل قطع صغيرة فور وصولها"""
    global _last_call
    messages = _build(system_prompt, history, user_text)

    async def run():
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        task = asyncio.create_task(asyncio.to_thread(_stream_worker, messages, queue, loop))
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            await task

    if is_keyed():
        async for c in run():
            yield c
    else:
        gap = float(config.KEYLESS.get("min_gap", 45))
        async with _lock:
            wait = gap - (time.monotonic() - _last_call)
            if wait > MAX_WAIT:
                raise BusyError("queue full")
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async for c in run():
                    yield c
            finally:
                _last_call = time.monotonic()


async def ask(system_prompt: str, history: list, user_text: str) -> str:
    """رد كامل (بدون بثّ)"""
    messages = _build(system_prompt, history, user_text)
    return await _guard(lambda: _plain_call(messages))


def image_url(prompt: str) -> str:
    return config.IMAGE_URL.format(urllib.parse.quote(prompt))
