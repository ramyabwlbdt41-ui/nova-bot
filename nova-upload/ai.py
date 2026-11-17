# -*- coding: utf-8 -*-
"""طبقة الذكاء الاصطناعي — بثّ حي (Streaming) + مزوّد مجاني بدون مفتاح"""

import asyncio
import json
import logging
import threading
import time
import urllib.parse
from typing import AsyncIterator

import requests

import config

log = logging.getLogger("nova.ai")


class AIError(Exception):
    """خطأ عام"""


class BusyError(AIError):
    """الخدمة مزدحمة — اطلب من المستخدم المحاولة لاحقاً"""


# ================= حالة الوضع المجاني =================
_lock = asyncio.Lock()
_last_call = 0.0
MAX_WAIT = 60

# ================= قاطع الدائرة =================
# لما المزوّد الأساسي يخلص رصيده أو يفشل، نتجاهله مؤقتاً ونروح للبديل فوراً
_down_until = 0.0
_down_reason = ""
_down_lock = threading.Lock()


def _mark_down(seconds: float, reason: str = ""):
    global _down_until, _down_reason
    with _down_lock:
        _down_until = max(_down_until, time.monotonic() + seconds)
        if reason:
            _down_reason = reason[:180]
    log.warning("primary down for %.0fs | %s", seconds, reason[:150])


def _is_down() -> bool:
    return time.monotonic() < _down_until


def _keyless_target():
    """المزوّد المجاني بدون مفتاح (بديل احتياطي)"""
    return (
        config.KEYLESS["base"],
        {"Content-Type": "application/json"},
        config.KEYLESS["models"],
    )


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


def _payload(model: str, messages: list, stream: bool, url: str = "") -> dict:
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": config.AI_MAX_TOKENS,
        "temperature": config.AI_TEMPERATURE,
        "stream": stream,
    }
    # Gemini: تعطيل التفكير العميق لردود فورية
    if "generativelanguage" in (url or ""):
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
def _stream_worker(messages, queue, loop, url=None, headers=None, models=None):
    url = url or _endpoint()
    headers = headers or _headers()
    models = models or _models()
    last = None
    for model in models:
        try:
            with requests.post(
                url, headers=headers,
                json=_payload(model, messages, True, url),
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


async def _plain_call(messages: list, url=None, headers=None, models=None) -> str:
    url = url or _endpoint()
    headers = headers or _headers()
    models = models or _models()
    last = None
    limited = 0
    started = time.monotonic()
    budget = 30.0                     # سقف زمني لكل المحاولات
    for model in models:
        left = budget - (time.monotonic() - started)
        if left <= 1:
            break
        try:
            r = requests.post(url, headers=headers,
                              json=_payload(model, messages, False, url),
                              timeout=min(config.AI_TIMEOUT, left))
            if r.status_code in (402, 404, 429):
                # موديل غير متاح أو حصته خلصت — جرّب الموديل التالي
                limited += 1
                last = AIError(f"{r.status_code}")
                continue
            if r.status_code >= 400:
                last = AIError(f"{r.status_code}: {r.text[:160]}")
                continue
            text = (r.json()["choices"][0]["message"]["content"] or "").strip()
            if text:
                return text
            last = AIError("رد فارغ")
        except requests.Timeout as e:
            # انقطاع شبكة عام — لا فائدة من تجربة بقية الموديلات
            raise AIError(f"timeout: {e}")
        except Exception as e:
            last = e
    if last is not None and limited == len(models):
        raise BusyError("rate limited")
    raise AIError(str(last) if last else "لا يوجد موديل")


async def _guard(coro_factory, keyless: bool = False):
    """ينفّذ الطلب داخل الطابور المجاني إن لم يوجد مفتاح"""
    global _last_call
    if is_keyed() and not keyless:
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


async def _agen(messages, url=None, headers=None, models=None):
    """مولّد قطع الرد من عامل الخيط"""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    task = asyncio.create_task(
        asyncio.to_thread(_stream_worker, messages, queue, loop, url, headers, models)
    )
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


async def stream(system_prompt: str, history: list, user_text: str) -> AsyncIterator[str]:
    """يرجع الرد على شكل قطع صغيرة فور وصولها — مع بديل تلقائي"""
    global _last_call
    messages = _build(system_prompt, history, user_text)

    if is_keyed() and not _is_down():
        try:
            got = False
            async for piece in _agen(messages):
                got = True
                yield piece
            if got:
                return
        except GeneratorExit:
            raise
        except BusyError as e:
            _mark_down(900, str(e))          # حصة يومية — بديل فوراً
        except Exception as e:
            _mark_down(180, str(e))

    # البديل المجاني بدون مفتاح
    gap = float(config.KEYLESS.get("min_gap", 4))
    async with _lock:
        wait = gap - (time.monotonic() - _last_call)
        if wait > MAX_WAIT:
            raise BusyError("queue full")
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async for piece in _agen(messages, *_keyless_target()):
                yield piece
        finally:
            _last_call = time.monotonic()


async def ask(system_prompt: str, history: list, user_text: str) -> str:
    """رد كامل (بدون بثّ) — مع بديل تلقائي عند نفاد الحصة"""
    messages = _build(system_prompt, history, user_text)

    if is_keyed() and not _is_down():
        try:
            return await _plain_call(messages)
        except BusyError as e:
            _mark_down(900, str(e))          # 15 دقيقة ثم نجرّب المفتاح ثانية
        except Exception as e:
            _mark_down(180, str(e))

    # البديل المجاني بدون مفتاح
    return await _guard(
        lambda: _plain_call(messages, *_keyless_target()),
        keyless=True,
    )


def image_url(prompt: str) -> str:
    return config.IMAGE_URL.format(urllib.parse.quote(prompt))


# ================= تشخيص سريع (للخدمة عن بُعد) =================
def diag() -> dict:
    """يختبر سلسلة المزوّدين ويرجّع أي موديل رد فعلاً"""
    msgs = [{"role": "user", "content": "قل: تم"}]
    out = {"keyed": is_keyed(), "down": _is_down()}
    t = time.time()
    try:
        out["ok"] = True
        out["reply"] = asyncio.run(_plain_call(msgs))
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)[:300]
    out["sec"] = round(time.time() - t, 1)
    out["models"] = list(_models())
    return out
