# -*- coding: utf-8 -*-
"""لوحات الأزرار — بتنسيق مميز"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import config


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("💬 ابدأ الدردشة", callback_data="m:chat"),
            InlineKeyboardButton("🖼 توليد صورة", callback_data="m:image"),
        ],
        [
            InlineKeyboardButton("✨ أفكار جاهزة", callback_data="m:ideas"),
            InlineKeyboardButton("🎭 الأسلوب", callback_data="m:mode"),
        ],
        [
            InlineKeyboardButton("👤 حسابي", callback_data="m:me"),
            InlineKeyboardButton("ℹ️ المساعدة", callback_data="m:help"),
        ],
        [
            InlineKeyboardButton("💬 الدعم", url=config.SUPPORT_URL),
            InlineKeyboardButton("✨ عن البوت", callback_data="m:about"),
        ],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("🛠 لوحة الإدارة", callback_data="adm:home")])
    return InlineKeyboardMarkup(rows)


def modes(current: str) -> InlineKeyboardMarkup:
    rows = []
    for key, data in config.MODES.items():
        mark = "✅ " if key == current else "◽ "
        rows.append([InlineKeyboardButton(f"{mark}{data['label']}", callback_data=f"mode:{key}")])
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="m:home")])
    return InlineKeyboardMarkup(rows)


def back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ رجوع", callback_data="m:home")],
    ])


def ideas() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(label, callback_data=f"idea:{key}")]
        for key, (label, _) in config.IDEAS.items()
    ]
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="m:home")])
    return InlineKeyboardMarkup(rows)


def after_action() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 اسألني شيئاً", callback_data="m:chat"),
            InlineKeyboardButton("🖼 صورة", callback_data="m:image"),
        ],
    ])


def limit_reached() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 الدعم", url=config.SUPPORT_URL)],
        [InlineKeyboardButton("👤 حسابي", callback_data="m:me")],
    ])


def error_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 حاول مجدداً", callback_data="m:chat")],
        [InlineKeyboardButton("💬 الدعم", url=config.SUPPORT_URL)],
    ])


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 الإحصائيات", callback_data="adm:stats"),
            InlineKeyboardButton("🔑 المفتاح", callback_data="adm:key"),
        ],
        [InlineKeyboardButton("📢 رسالة جماعية", callback_data="adm:cast")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="m:home")],
    ])


def home_only() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 القائمة", callback_data="m:home")],
    ])
