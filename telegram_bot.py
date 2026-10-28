import os
import re
import logging
import threading
from functools import wraps
import telebot
from sheets_client import add_expense_row, get_monthly_expenses_summary

logger = logging.getLogger(__name__)

MONTH_NAMES = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]


def get_allowed_user_ids() -> set[int]:
    """Parse comma-separated allowed Telegram user IDs from env."""
    raw = os.getenv("ALLOWED_TELEGRAM_USER_IDS", "").strip()
    if not raw:
        return set()
    user_ids = set()
    for uid_str in raw.split(","):
        uid_str = uid_str.strip()
        if uid_str.isdigit():
            user_ids.add(int(uid_str))
    return user_ids


def restricted(func):
    """Decorator to verify if sender user id is in ALLOWED_TELEGRAM_USER_IDS."""
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        allowed_ids = get_allowed_user_ids()
        user_id = message.from_user.id if message.from_user else None
        if allowed_ids and user_id not in allowed_ids:
            logger.warning(f"Unauthorized access by Telegram user_id={user_id}")
            return
        return func(message, *args, **kwargs)
    return wrapper


def create_bot(sheets_service) -> telebot.TeleBot | None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set. Telegram bot disabled.")
        return None

    bot = telebot.TeleBot(token, parse_mode="HTML")

    @bot.message_handler(commands=['start', 'help'])
    @restricted
    def handle_help(message):
        help_text = (
            "👋 <b>Финансовый помощник</b>\n\n"
            "Доступные команды:\n"
            "• <code>/add [сумма] [категория] [описание]</code>\n"
            "  <i>Примеры:</i>\n"
            "  <code>/add 15 кафе</code>\n"
            "  <code>/add 25.50 транспорт такси</code>\n\n"
            "• <code>/summary</code> — расходы за текущий месяц\n"
            "• <code>/help</code> — помощь"
        )
        bot.reply_to(message, help_text)

    @bot.message_handler(commands=['add'])
    @restricted
    def handle_add(message):
        text = message.text.strip()
        parts = text.split(maxsplit=3)
        if len(parts) < 3:
            bot.reply_to(
                message,
                "⚠️ Формат: <code>/add [сумма] [категория] [описание]</code>\n"
                "Пример: <code>/add 15 кафе обед</code>"
            )
            return

        raw_amount = parts[1].replace(',', '.')
        category = parts[2].strip().capitalize()
        description = parts[3] if len(parts) > 3 else ""

        try:
            amount_val = float(raw_amount)
            if amount_val <= 0:
                raise ValueError()
        except ValueError:
            bot.reply_to(message, "⚠️ Укажите положительное число (напр. <code>15</code> или <code>15.50</code>).")
            return

        try:
            row = add_expense_row(
                sheets_service=sheets_service,
                amount=amount_val,
                category=category,
                description=description
            )
            date_str, amount_str, currency, cat, desc = row
            desc_text = f" ({desc})" if desc else ""
            reply_text = (
                f"✅ <b>Расход записан!</b>\n"
                f"• Дата: {date_str}\n"
                f"• Сумма: <b>{float(amount_str):.2f} {currency}</b>\n"
                f"• Категория: <b>{cat}</b>{desc_text}"
            )
            bot.reply_to(message, reply_text)
        except Exception as e:
            logger.error(f"Error adding expense from Telegram: {e}", exc_info=True)
            bot.reply_to(message, f"❌ Ошибка при записи в таблицу: {e}")

    @bot.message_handler(commands=['summary'])
    @restricted
    def handle_summary(message):
        try:
            summary = get_monthly_expenses_summary(sheets_service)
            month = summary['month']
            month_name = MONTH_NAMES[month] if 1 <= month <= 12 else str(month)
            currency = summary['currency']
            grand_total = summary['grand_total']
            by_category = summary['by_category']

            if not by_category and grand_total == 0.0:
                bot.reply_to(message, f"ℹ️ В {month_name} {summary['year']} расходов пока нет.")
                return

            sorted_cats = sorted(by_category.items(), key=lambda item: item[1], reverse=True)
            lines = [f"📊 <b>Расходы за {month_name} {summary['year']}</b>:\n"]
            for cat, amount in sorted_cats:
                lines.append(f"• {cat}: <b>{amount:.2f} {currency}</b>")

            lines.append("────────────────")
            lines.append(f"💰 <b>Всего: {grand_total:.2f} {currency}</b>")
            lines.append(f"<i>(Транзакций: {summary['transaction_count']})</i>")
            bot.reply_to(message, "\n".join(lines))
        except Exception as e:
            logger.error(f"Error generating summary: {e}", exc_info=True)
            bot.reply_to(message, f"❌ Ошибка получения сводки: {e}")

    return bot


def start_bot_thread(sheets_service) -> tuple[telebot.TeleBot | None, threading.Thread | None]:
    """Start the Telegram bot polling in a background daemon thread."""
    bot = create_bot(sheets_service)
    if not bot:
        return None, None

    def run_polling():
        logger.info("Telegram bot polling started.")
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            logger.error(f"Telegram bot polling exception: {e}", exc_info=True)
        finally:
            logger.info("Telegram bot polling stopped.")

    thread = threading.Thread(target=run_polling, daemon=True, name="TelegramBotPolling")
    thread.start()
    return bot, thread

