import os
import re
import logging

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("eng_school_bot")

# Состояния диалога
WHO, GOAL, AGE, FORMAT, LEVEL, SCHEDULE, CONTACT, CONFIRM = range(8)

YES_NO_KB = ReplyKeyboardMarkup([["Да", "Нет"]], resize_keyboard=True)

def _clean_text(s: str) -> str:
    return (s or "").strip()

def _is_child_flow(data: dict) -> bool:
    who = (data.get("who") or "").lower()
    return ("реб" in who) or ("дете" in who) or ("ребён" in who)

def _looks_like_phone(s: str) -> bool:
    # простая проверка: +7..., 7..., 8..., 10-15 цифр
    digits = re.sub(r"\D+", "", s or "")
    return 10 <= len(digits) <= 15

def _greet() -> str:
    return "Привет! Давай быстро разберёмся и подберём вариант 🙂"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        _greet() + "\nДля себя курс ищешь или для ребёнка?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return WHO

async def who(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["who"] = _clean_text(update.message.text)
    await update.message.reply_text(
        "Ок. Какая цель: разговорный, работа, учёба, переезд или экзамен?"
    )
    return GOAL

async def goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["goal"] = _clean_text(update.message.text)

    # если ребёнок — возраст обязателен
    if _is_child_flow(context.user_data):
        await update.message.reply_text("Сколько лет ребёнку?")
        return AGE

    await update.message.reply_text("Онлайн или офлайн удобнее?")
    return FORMAT

async def age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["age"] = _clean_text(update.message.text)
    await update.message.reply_text("Онлайн или офлайн удобнее?")
    return FORMAT

async def fmt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["format"] = _clean_text(update.message.text)
    await update.message.reply_text("Уровень примерно знаешь? Если нет — так и напиши: “не знаю”.")
    return LEVEL

async def level(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["level"] = _clean_text(update.message.text)
    await update.message.reply_text("По времени как удобнее: утро/день/вечер? И будни или выходные?")
    return SCHEDULE

async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["schedule"] = _clean_text(update.message.text)

    # короткий “человеческий” итог + CTA на пробный
    who_txt = context.user_data.get("who", "для себя")
    goal_txt = context.user_data.get("goal", "")
    fmt_txt = context.user_data.get("format", "")
    lvl_txt = context.user_data.get("level", "")

    summary = f"Ок, понял(а): {who_txt}, цель — {goal_txt}, формат — {fmt_txt}, уровень — {lvl_txt}."
    cta = "Предлагаю начать с пробного урока: там быстро определим уровень и подберём план. Записать тебя?"
    await update.message.reply_text(summary + "\n" + cta, reply_markup=YES_NO_KB)
    return CONFIRM

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ans = _clean_text(update.message.text).lower()

    if ans.startswith("д"):
        await update.message.reply_text(
            "Супер. Напиши, пожалуйста, имя и номер телефона/WhatsApp (можно одним сообщением).",
            reply_markup=ReplyKeyboardRemove(),
        )
        return CONTACT

    # если “нет” — мягко выяснить стоппер
    await update.message.reply_text(
        "Ок. Что больше стопорит: цена, время или сомнения по уровню?"
    )
    return CONFIRM  # остаёмся здесь и ждём ответ, после чего снова предложим пробный

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = _clean_text(update.message.text)
    context.user_data["contact_raw"] = text

    # попытка вытащить телефон, если есть
    phone_digits = re.sub(r"\D+", "", text)
    context.user_data["phone_digits"] = phone_digits if _looks_like_phone(text) else ""

    # финальное сообщение клиенту
    await update.message.reply_text(
        "Принято ✅ Передам менеджеру, чтобы он/она связались с тобой. "
        "Если хочешь — напиши ещё, в какое время лучше писать/звонить."
    )

    # Здесь можно: отправить лид в CRM / Google Sheets / менеджеру в чат
    # Сейчас просто логируем
    log.info("LEAD: %s", context.user_data)

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Ок, остановились. Если что — напиши /start.")
    return ConversationHandler.END

def main():
    token = os.getenv("BOT_TOKEN") or 'your_token'
    if not token:
        raise RuntimeError("Не найден BOT_TOKEN в переменных окружения")

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WHO: [MessageHandler(filters.TEXT & ~filters.COMMAND, who)],
            GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, goal)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age)],
            FORMAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, fmt)],
            LEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, level)],
            SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()
