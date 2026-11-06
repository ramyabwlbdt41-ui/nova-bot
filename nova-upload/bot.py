# -*- coding: utf-8 -*-
"""✨ نوفا — بوت ذكاء اصطناعي عربي، مجاني بالكامل، بتجربة مميزة"""

import asyncio
import html
import http.server
import logging
import os
import random
import socket
import threading
import time

import requests

from telegram import (
    BotCommand,
    InputFile,
    LinkPreviewOptions,
    ReactionTypeEmoji,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, Conflict, RetryAfter, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Defaults,
    MessageHandler,
    filters,
)

import ai
import config
import keyboards as kb
import media
from config import TOKEN
from db import DB

logging.basicConfig(
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("nova")

db = DB(config.DB_PATH)
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
_instance_lock = None


# ================= أدوات =================
def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def split_text(text: str, size: int = 4000):
    if len(text) <= size:
        return [text]
    parts, current = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > size:                 # سطر أطول من الحد
            parts.append(line[:size])
            line = line[size:]
        if len(current) + len(line) > size:
            parts.append(current)
            current = ""
        current += line
    if current:
        parts.append(current)
    return parts


async def react(message, emoji: str):
    """رياكشن بصري على رسالة المستخدم"""
    if not config.REACTIONS:
        return
    try:
        await message.set_reaction([ReactionTypeEmoji(emoji=emoji)])
    except TelegramError:
        pass


async def random_sticker(context: ContextTypes.DEFAULT_TYPE):
    """(اختياري) file_id لملصق عشوائي — يُستخدم فقط إن فعّلت STICKER_ON_START"""
    packs = context.bot_data.get("stickers")
    if packs is None:
        packs = []
        for name in config.STICKER_PACKS:
            try:
                s = await context.bot.get_sticker_set(name)
                packs.extend([st.file_id for st in s.stickers])
            except TelegramError as e:
                log.warning("sticker pack %s: %s", name, e)
        context.bot_data["stickers"] = packs
    return random.choice(packs) if packs else None


async def ensure_user(update: Update):
    u = update.effective_user
    return db.ensure_user(u.id, u.username or "", u.first_name or "صديقي")


def mode_label(key: str) -> str:
    return config.MODES.get(key, config.MODES["chat"])["label"]


def cool_down_ok(context: ContextTypes.DEFAULT_TYPE) -> bool:
    now = time.time()
    if now - context.user_data.get("last", 0) < config.COOLDOWN:
        return False
    context.user_data["last"] = now
    return True


# ================= الترحيب =================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row, is_new = await ensure_user(update)
    caption = config.WELCOME.format(
        name=config.BOT_NAME,
        tagline=config.TAGLINE,
        first=html.escape(row["first_name"] or "صديقي"),
        daily=config.DAILY_LIMIT,
    )
    markup = kb.main_menu(is_admin(update.effective_user.id))
    effect = config.MESSAGE_EFFECT

    # البطاقة الفخمة
    banner = os.path.join(config.BASE_DIR, "assets", "banner.png")
    if not os.path.exists(banner):
        banner = os.path.join(config.BASE_DIR, "banner.png")
    sent = False

    async def send_text():
        try:
            await update.message.reply_text(
                caption, reply_markup=markup, message_effect_id=effect
            )
        except TelegramError:
            await update.message.reply_text(caption, reply_markup=markup)
        return None

    if os.path.exists(banner):
        try:
            with open(banner, "rb") as f:
                msg = await update.message.reply_photo(
                    photo=InputFile(f, filename="nova.png"),
                    caption=caption,
                    reply_markup=markup,
                    message_effect_id=effect,
                )
            sent = True
        except TelegramError:
            try:
                with open(banner, "rb") as f:
                    await update.message.reply_photo(
                        photo=InputFile(f, filename="nova.png"),
                        caption=caption,
                        reply_markup=markup,
                    )
                sent = True
            except TelegramError:
                sent = False

    if not sent:
        await send_text()

    await react(update.message, "🔥")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(config.HELP_TEXT, reply_markup=kb.back_home())


async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        config.ABOUT_TEXT.format(
            name=config.BOT_NAME,
            tagline=config.TAGLINE,
            support=config.SUPPORT_USER,
        ),
        reply_markup=kb.back_home(),
    )


async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row, _ = await ensure_user(update)
    await update.message.reply_text(
        config.ACCOUNT_TEXT.format(
            first=html.escape(row["first_name"] or "صديقي"),
            mode=mode_label(row["mode"]),
            used=db.today_usage(row["user_id"]),
            limit=config.DAILY_LIMIT,
            total=row["used_total"],
            since=(row["created_at"] or "")[:10],
        ),
        reply_markup=kb.back_home(),
    )


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.reset_history(update.effective_user.id)
    context.user_data.pop("last", None)
    await update.message.reply_text(config.NEW_TEXT, reply_markup=kb.home_only())


async def cmd_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row, _ = await ensure_user(update)
    await update.message.reply_text(
        config.MODE_MENU.format(current=mode_label(row["mode"])),
        reply_markup=kb.modes(row["mode"]),
    )


async def cmd_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(config.IMAGE_MENU, reply_markup=kb.back_home())


async def cmd_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _cmd_media(update, context, "song")


async def cmd_nasheed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _cmd_media(update, context, "nasheed")


async def cmd_podcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _cmd_media(update, context, "podcast")


async def _cmd_media(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str):
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text(config.MEDIA_HINT)
        return
    await _handle_media(update.message, context, query, kind)


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لعرض رقم الحساب — لضبط ADMIN_IDS"""
    u = update.effective_user
    await update.message.reply_text(
        f"🆔 <b>رقمك:</b> <code>{u.id}</code>\n\n"
        "<blockquote>ضعه في <code>ADMIN_IDS</code> داخل config.py لتفعيل لوحة الإدارة.</blockquote>"
    )


# ================= الإدارة =================
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("<b>🛠 لوحة الإدارة</b>", reply_markup=kb.admin_menu())


async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        uid = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("الاستخدام: <code>/ban 123456789</code>")
        return
    db.set_banned(uid, True)
    await update.message.reply_text(f"🚫 تم حظر <code>{uid}</code>")


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        uid = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("الاستخدام: <code>/unban 123456789</code>")
        return
    db.set_banned(uid, False)
    await update.message.reply_text(f"✅ تم فك الحظر عن <code>{uid}</code>")


USAGE_SETKEY = """\
<b>🔑 تشغيل الوضع السريع</b>
━━━━━━━━━━━━━━

<blockquote>أرسل مفتاحك بهذه الصيغة:

<code>/setkey gemini AIza...</code>
<code>/setkey groq gsk_...</code>
<code>/setkey openrouter sk-or-...</code></blockquote>

<b>المزوّدون المجانيون:</b>
• Gemini ← aistudio.google.com/apikey
• Groq ← console.groq.com/keys
• OpenRouter ← openrouter.ai/keys"""


async def cmd_setkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(USAGE_SETKEY)
        return

    provider, key = args[0].lower(), args[1].strip()
    if provider not in config.PROVIDERS:
        await update.message.reply_text(
            f"⚠️ مزوّد غير معروف: <code>{html.escape(provider)}</code>\n"
            "المتاح: gemini · groq · openrouter"
        )
        return

    old = (config.AI_KEY, config.AI_BASE, config.AI_MODELS)
    config.AI_BASE, config.AI_MODELS = config.PROVIDERS[provider]
    config.AI_KEY = key

    notice = await update.message.reply_text("🔍 أختبر المفتاح…")
    try:
        reply = await ai.ask("أجب بكلمة واحدة فقط.", [], "قل: تم")
    except Exception as e:
        config.AI_KEY, config.AI_BASE, config.AI_MODELS = old
        await notice.edit_text(
            f"❌ <b>المفتاح لم يعمل</b>\n\n<blockquote>{html.escape(str(e)[:200])}</blockquote>\n"
            "تأكد أنك نسخت المفتاح كاملاً."
        )
        return

    try:
        import json
        path = os.path.join(config.DATA_DIR, "provider.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"provider": provider, "key": key}, f)
    except Exception as e:
        await notice.edit_text(f"⚠️ عمل المفتاح لكن تعذّر حفظه: {e}")
        return

    await notice.edit_text(
        f"⚡ <b>تم تفعيل الوضع السريع</b>\n━━━━━━━━━━━━━━\n\n"
        f"<blockquote>المزوّد: <b>{provider}</b>\n"
        f"اختبار الرد: {html.escape(reply[:40])}</blockquote>\n\n"
        "الآن الردود فورية بدون انتظار ✅"
    )


async def cmd_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if ai.is_keyed():
        provider = next(
            (n for n, (b, _) in config.PROVIDERS.items() if b == config.AI_BASE),
            "مخصص",
        )
        await update.message.reply_text(
            f"⚡ <b>الوضع السريع مفعّل</b>\n\n<blockquote>المزوّد: <b>{provider}</b>\n"
            f"الموديل: <code>{config.AI_MODELS[0]}</code></blockquote>"
        )
    else:
        await update.message.reply_text(
            "🐢 <b>الوضع المجاني (بطيء)</b>\n\n"
            "<blockquote>يعمل بدون مفتاح، لكن بحد رسالة كل 45 ثانية.</blockquote>\n"
            + USAGE_SETKEY
        )


# ================= الأزرار =================
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    row, _ = await ensure_user(update)
    data = q.data
    admin = is_admin(update.effective_user.id)

    async def show(text, markup=None):
        try:
            await q.edit_message_text(text, reply_markup=markup)
        except BadRequest:
            await q.message.reply_text(text, reply_markup=markup)

    if data == "m:home":
        await show(
            config.WELCOME.format(
                name=config.BOT_NAME,
                tagline=config.TAGLINE,
                first=html.escape(row["first_name"] or "صديقي"),
                daily=config.DAILY_LIMIT,
            ),
            kb.main_menu(admin),
        )
    elif data == "m:chat":
        await show(
            "<b>💬 أنا جاهز</b>\n\n<blockquote>اكتب سؤالك الآن 👇</blockquote>",
            kb.back_home(),
        )
    elif data == "m:image":
        await show(config.IMAGE_MENU, kb.back_home())
    elif data == "m:media":
        await show(config.MEDIA_MENU, kb.back_home())
    elif data.startswith("mdl:"):
        try:
            idx = int(data.split(":", 1)[1])
        except ValueError:
            return
        await _send_media(update, context, idx)
    elif data == "m:mode":
        await show(config.MODE_MENU.format(current=mode_label(row["mode"])), kb.modes(row["mode"]))
    elif data == "m:ideas":
        await show(config.IDEAS_TEXT, kb.ideas())
    elif data.startswith("idea:"):
        key = data.split(":", 1)[1]
        item = config.IDEAS.get(key)
        if not item:
            return
        uid = update.effective_user.id
        if db.today_usage(uid) >= config.DAILY_LIMIT:
            await q.message.reply_text(
                config.LIMIT_TEXT.format(limit=config.DAILY_LIMIT, name=config.BOT_NAME),
                reply_markup=kb.limit_reached(),
            )
            return
        await _handle_chat(context, q.message.chat_id, uid, item[1], row)
    elif data.startswith("mode:"):
        key = data.split(":", 1)[1]
        if key in config.MODES:
            db.set_mode(update.effective_user.id, key)
            await show(config.MODE_MENU.format(current=mode_label(key)), kb.modes(key))
    elif data == "m:me":
        await show(
            config.ACCOUNT_TEXT.format(
                first=html.escape(row["first_name"] or "صديقي"),
                mode=mode_label(row["mode"]),
                used=db.today_usage(row["user_id"]),
                limit=config.DAILY_LIMIT,
                total=row["used_total"],
                since=(row["created_at"] or "")[:10],
            ),
            kb.back_home(),
        )
    elif data == "m:help":
        await show(config.HELP_TEXT, kb.back_home())
    elif data == "m:about":
        await show(
            config.ABOUT_TEXT.format(
                name=config.BOT_NAME, tagline=config.TAGLINE, support=config.SUPPORT_USER
            ),
            kb.back_home(),
        )
    elif data == "adm:home" and admin:
        await show("<b>🛠 لوحة الإدارة</b>", kb.admin_menu())
    elif data == "adm:stats" and admin:
        s = db.stats()
        await show(
            "<b>📊 الإحصائيات</b>\n━━━━━━━━━━━━━━\n\n"
            f"<blockquote>👥 المستخدمون: <b>{s['users']}</b>\n"
            f"🟢 نشطون اليوم: <b>{s['active']}</b>\n"
            f"💬 رسائل اليوم: <b>{s['today']}</b>\n"
            f"📈 الإجمالي: <b>{s['total']}</b></blockquote>",
            kb.admin_menu(),
        )
    elif data == "adm:key" and admin:
        if ai.is_keyed():
            provider = next(
                (n for n, (b, _) in config.PROVIDERS.items() if b == config.AI_BASE),
                "مخصص",
            )
            await show(
                f"⚡ <b>الوضع السريع مفعّل</b>\n\n"
                f"<blockquote>المزوّد: <b>{provider}</b>\n"
                f"الموديل: <code>{config.AI_MODELS[0]}</code></blockquote>\n\n"
                "لتغيير المفتاح: <code>/setkey gemini AIza...</code>",
                kb.admin_menu(),
            )
        else:
            await show(USAGE_SETKEY, kb.admin_menu())
    elif data == "adm:cast" and admin:
        context.user_data["await_cast"] = True
        await show(
            "<b>📢 الرسالة الجماعية</b>\n\n<blockquote>أرسل الآن نص الرسالة.</blockquote>",
            kb.admin_menu(),
        )


# ================= الرسائل =================
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user

    # إرسال جماعي
    if context.user_data.get("await_cast") and is_admin(u.id):
        context.user_data["await_cast"] = False
        ids = db.all_user_ids()
        sent = 0
        for uid in ids:
            try:
                await context.bot.send_message(uid, update.message.text)
                sent += 1
                await asyncio.sleep(0.05)
            except TelegramError:
                continue
        await update.message.reply_text(f"✅ أُرسلت إلى {sent} من {len(ids)}.")
        return

    if db.is_banned(u.id):
        return

    row, _ = await ensure_user(update)
    text = (update.message.text or "").strip()
    if not text:
        return
    if len(text) > config.MAX_INPUT:
        await update.message.reply_text(
            f"⚠️ الرسالة طويلة — الحد <b>{config.MAX_INPUT}</b> حرف."
        )
        return
    if not cool_down_ok(context):
        return

    lowered = text.lower()
    is_image = config.IMAGE_ENABLED and (
        lowered.startswith("صورة:") or lowered.startswith("صورة ") or lowered.startswith("image:")
    )

    if db.today_usage(u.id) >= config.DAILY_LIMIT:
        await update.message.reply_text(
            config.LIMIT_TEXT.format(limit=config.DAILY_LIMIT, name=config.BOT_NAME),
            reply_markup=kb.limit_reached(),
        )
        return

    await react(update.message, config.REACTION_WAIT)

    if is_image:
        await _handle_image(update, context, text, row)
        return

    # 🎵 طلب نشيد/أغنية/بودكاست بالكلام العادي
    if media.available():
        media_query, media_kind = media.detect(text)
        if media_query:
            await _handle_media(update.message, context, media_query, media_kind)
            return

    await _handle_chat(
        context, update.effective_chat.id, u.id, text, row, update.message
    )


async def _handle_chat(context, chat_id, user_id, text, row, message=None):
    mode = row["mode"] if row["mode"] in config.MODES else "chat"
    system_prompt = config.MODES[mode]["prompt"]
    history = db.history(user_id, config.MEMORY_TURNS * 2)

    try:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        notice = await context.bot.send_message(chat_id, "▌")
    except TelegramError:
        return

    buf = ""
    last_edit = 0.0
    state = {"started": False}

    async def hint():
        await asyncio.sleep(7)
        if not state["started"]:
            try:
                await notice.edit_text(
                    "⏳ <b>لحظة…</b>\n\n<blockquote>أجهّز الرد.</blockquote>"
                )
            except TelegramError:
                pass

    hint_task = asyncio.create_task(hint())
    try:
        if ai.supports_stream():
            async for piece in ai.stream(system_prompt, history, text):
                buf += piece
                if not state["started"]:
                    state["started"] = True
                    hint_task.cancel()
                    last_edit = 0.0
                now = time.monotonic()
                if now - last_edit >= 1.8:
                    last_edit = now
                    preview = buf[-3800:] + "▌"
                    try:
                        await notice.edit_text(preview, parse_mode=None)
                    except RetryAfter as e:
                        last_edit = time.monotonic() + e.retry_after
                    except TelegramError:
                        pass
        else:
            await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
            buf = await ai.ask(system_prompt, history, text)
            state["started"] = True
            hint_task.cancel()
    except ai.BusyError:
        hint_task.cancel()
        await _replace(notice, config.BUSY_TEXT, kb.error_menu())
        return
    except Exception as e:
        hint_task.cancel()
        log.warning("ai error: %s", e)
        if not buf.strip():
            await _replace(notice, config.ERROR_TEXT, kb.error_menu())
            return
    finally:
        hint_task.cancel()

    answer = buf.strip()
    if not answer:
        await _replace(notice, "🤔 لم أجد إجابة، جرّب صياغة أخرى.")
        return

    parts = split_text(answer)
    try:
        await notice.edit_text(parts[0], parse_mode=None,
                               link_preview_options=NO_PREVIEW)
    except TelegramError:
        pass
    for part in parts[1:]:
        await context.bot.send_message(chat_id, part, parse_mode=None,
                                       link_preview_options=NO_PREVIEW)

    db.consume(user_id, config.DAILY_LIMIT)
    db.add_message(user_id, "user", text)
    db.add_message(user_id, "assistant", answer)

    if message is not None:
        await react(message, config.REACTION_DONE)


async def _handle_image(update, context, text, row):
    prompt = text.split(":", 1)[-1] if ":" in text else text.split(" ", 1)[-1]
    prompt = prompt.strip()
    if not prompt:
        await update.message.reply_text(
            "🖼 اكتب مثلاً: <code>صورة: قطة رائد فضاء على القمر</code>"
        )
        return

    notice = await update.message.reply_text(config.GENERATING)
    slow = asyncio.create_task(_slow_notice(notice))
    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_PHOTO)
        url = ai.image_url(prompt)
        await update.message.reply_photo(photo=url, caption=f"🖼 {prompt[:900]}")
        slow.cancel()
        db.consume(update.effective_user.id, config.DAILY_LIMIT)
        await react(update.message, config.REACTION_DONE)
    except Exception as e:
        slow.cancel()
        log.warning("image error: %s", e)
        await _replace(
            notice,
            "⚠️ <b>تعذّر رسم الصورة</b>\n\n<blockquote>جرّب وصفاً آخر أو أبسط.</blockquote>",
            kb.error_menu(),
        )
        return
    await _replace(notice, None)


async def _handle_media(message, context, query: str, kind: str):
    """بحث عن مقطع صوتي وعرض النتائج كأزرار"""
    label = config.MEDIA_LABELS.get(kind, "🎵")
    notice = await message.reply_text(
        f"{label} <b>أبحث عن:</b> {html.escape(query)}\n\n"
        "<blockquote>لحظات…</blockquote>"
    )
    try:
        await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)
    except TelegramError:
        pass

    results = await media.search(query)
    if not results:
        await _replace(
            notice,
            "😕 <b>ما لقيت نتائج</b>\n\n<blockquote>جرّب كلمات أقل أو أبسط.</blockquote>",
            kb.error_menu(),
        )
        return

    context.user_data["media"] = results
    context.user_data["media_kind"] = kind

    lines = [f"{label} <b>نتائج البحث</b>", "━━━━━━━━━━━━━━", ""]
    for i, item in enumerate(results, 1):
        dur = media.fmt_duration(item.get("duration"))
        extra = f" · <i>{dur}</i>" if dur else ""
        lines.append(f"<b>{i}.</b> {html.escape((item.get('title') or '')[:80])}{extra}")
    lines += ["", "<blockquote>اضغط على الرقم لتحميل الصوت 🎧</blockquote>"]
    await _replace(notice, "\n".join(lines), kb.media_results(results))


async def _send_media(update, context, index: int):
    """تحميل النتيجة المختارة وإرسالها كملف صوتي"""
    q = update.callback_query
    items = context.user_data.get("media") or []
    if index < 0 or index >= len(items):
        await q.answer("انتهت النتائج — ابحث من جديد", show_alert=True)
        return

    uid = update.effective_user.id
    if db.today_usage(uid) >= config.DAILY_LIMIT:
        await q.answer("وصلت للحد اليومي", show_alert=True)
        return

    item = items[index]
    try:
        await q.answer("⏳ جاري تحميل الصوت…")
    except TelegramError:
        pass
    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_VOICE)
    except TelegramError:
        pass

    path = await media.download(item.get("url", ""), media.key_from_url(item.get("url", "")))
    if not path:
        await q.message.reply_text(
            "🔗 <b>ما قدرت أنزّل الملف</b>\n\n"
            f"<blockquote>افتح الرابط مباشرة:\n{item.get('url', '')}</blockquote>"
        )
        return

    try:
        with open(path, "rb") as f:
            await q.message.reply_audio(
                audio=f,
                title=(item.get("title") or "مقطع")[:64],
                performer=(item.get("uploader") or config.BOT_NAME)[:64],
                duration=int(item.get("duration") or 0),
            )
        db.consume(uid, config.DAILY_LIMIT)
    except TelegramError as e:
        log.warning("audio send: %s", e)
        await q.message.reply_text(f"🔗 {item.get('url', '')}")


async def _slow_notice(notice):
    """بعد 8 ثوانٍ من الانتظار يُظهر رسالة طابور بدل الصمت"""
    try:
        await asyncio.sleep(8)
        await notice.edit_text(
            "⏳ <b>لحظة…</b>\n\n<blockquote>الخدمة مزدحمة قليلاً، أجهّز ردك.</blockquote>"
        )
    except (asyncio.CancelledError, TelegramError):
        pass


async def _replace(notice, text, markup=None):
    """يحذف رسالة الانتظار أو يحوّلها لرسالة خطأ"""
    try:
        if text is None:
            await notice.delete()
        else:
            await notice.edit_text(text, reply_markup=markup)
    except TelegramError:
        if text is not None:
            try:
                await notice.reply_text(text, reply_markup=markup)
            except TelegramError:
                pass


# ================= الأخطاء =================
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, Conflict):
        log.error("تعارض: البوت يعمل في نسخة أخرى. أغلق النوافذ الزائدة.")
        return
    log.exception("خطأ غير متوقع", exc_info=context.error)


# ================= الإعداد عند التشغيل =================
async def post_init(app: Application):
    try:
        await app.bot.set_my_commands(
            [BotCommand(cmd, desc) for cmd, desc in config.COMMANDS]
        )
        await app.bot.set_my_short_description(
            f"✨ {config.BOT_NAME} — {config.TAGLINE}. مجاني بالكامل."
        )
        await app.bot.set_my_description(
            f"✨ {config.BOT_NAME} — {config.TAGLINE}\n\n"
            "محادثة ذكية · كتابة · برمجة · شرح · ترجمة · توليد صور.\n"
            f"مجاني بالكامل — {config.DAILY_LIMIT} رسالة يومياً.\n\n"
            f"الدعم: {config.SUPPORT_USER}"
        )
    except TelegramError as e:
        log.warning("profile setup: %s", e)


def build_app() -> Application:
    app = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(20)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(10)
        .defaults(Defaults(parse_mode=ParseMode.HTML, link_preview_options=NO_PREVIEW))
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("about", cmd_about))
    app.add_handler(CommandHandler("me", cmd_me))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("mode", cmd_mode))
    app.add_handler(CommandHandler("image", cmd_image))
    app.add_handler(CommandHandler("song", cmd_song))
    app.add_handler(CommandHandler("nasheed", cmd_nasheed))
    app.add_handler(CommandHandler("podcast", cmd_podcast))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("setkey", cmd_setkey))
    app.add_handler(CommandHandler("key", cmd_key))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    return app


# ================= الاستضافة (Render / Koyeb / VPS) =================
def start_health_server():
    """سيرفر HTTP صغير — بعض المنصّات تطلب منفذاً لتعرف أن التطبيق حيّ"""
    port = int(os.getenv("PORT", "0") or "0")
    if not port:
        return

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"OK"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info("🌐 health server على المنفذ %s", port)


def start_keepalive():
    """يمنع الاستضافة المجانية من إيقاف البوت عند الخمول"""
    url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("KEEP_ALIVE_URL")
    if not url:
        return

    def loop():
        while True:
            time.sleep(600)          # كل 10 دقائق
            try:
                requests.get(url, timeout=30)
            except Exception:
                pass

    threading.Thread(target=loop, daemon=True).start()
    log.info("🔁 keep-alive → %s", url)


async def serve(app: Application):
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=False, bootstrap_retries=5)
    start_health_server()
    start_keepalive()
    log.info("✨ %s يعمل الآن", config.BOT_NAME)
    try:
        await asyncio.Event().wait()      # يبقى شغّالاً
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def main():
    if not TOKEN:
        raise SystemExit(
            "❌ لا يوجد توكن.\n"
            "ضع BOT_TOKEN في ملف .env (محلياً) أو في متغيرات البيئة (على الاستضافة)."
        )

    # يمنع تشغيل نسختين في نفس الوقت (يسبب تعارض تيليجرام)
    global _instance_lock
    _instance_lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _instance_lock.bind(("127.0.0.1", 47823))
        _instance_lock.listen(1)
    except OSError:
        raise SystemExit(
            "\n⚠️  البوت يعمل بالفعل في نافذة أخرى.\n"
            "أغلق النافذة القديمة أولاً ثم شغّل هذا الملف.\n"
        )

    app = build_app()
    try:
        asyncio.run(serve(app))
    except (KeyboardInterrupt, SystemExit):
        log.info("تم الإيقاف.")


if __name__ == "__main__":
    main()
