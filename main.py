import os
import re
import sys
import time
import signal
import socket
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from gmail_pop import EmailClient
from sheets_client import init_sheets_service, append_rows
from telegram_bot import start_bot_thread

# Setup logging with rotating file handler
log_handler = RotatingFileHandler("service.log", maxBytes=5 * 1024 * 1024, backupCount=3)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        log_handler,
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets'
]

# Force IPv4 resolution if configured (default: true)
if os.getenv('FORCE_IPV4', 'true').lower() in ('true', '1'):
    orig_getaddrinfo = socket.getaddrinfo

    def forced_ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = forced_ipv4_getaddrinfo

# Handle termination signals gracefully
running = True

def handle_exit_signal(signum, frame):
    global running
    logger.info(f"Received exit signal ({signum}). Exiting gracefully...")
    running = False

signal.signal(signal.SIGINT, handle_exit_signal)
signal.signal(signal.SIGTERM, handle_exit_signal)


def parse_amount_and_currency(raw_amount: str | None) -> tuple[str, str]:
    """Parse raw amount string like '12.50 BYN' or '1 250.00 BYN' into amount and currency."""
    if not raw_amount:
        return '', ''
    cleaned = raw_amount.replace('\xa0', ' ').strip()
    match = re.match(r'^([\d\s.,]+)\s*([A-Za-zА-Яа-я]+)$', cleaned)
    if match:
        amount_part, curr_part = match.groups()
        return amount_part.replace(' ', ''), curr_part
    parts = cleaned.rsplit(' ', 1)
    if len(parts) == 2:
        return parts[0].replace(' ', ''), parts[1]
    return cleaned, ''


def parse_with_own_brains(message: dict) -> dict:
    """Parse transaction details from email message body and headers."""
    body = message.get('body') or ''
    date_val = message.get('date')
    date_str = str(date_val.date()) if hasattr(date_val, 'date') else str(date_val or '')

    parsed = {
        'date': date_str,
        'success': 'Успешно' in body
    }
    if not parsed['success']:
        logger.info(f"Unsuccessful transaction: {message.get('subject')}. Ignoring it..")
        return parsed

    body_lines = [line.strip() for line in body.splitlines() if line.strip()]

    # Extract key-value pairs separated by ':'
    for line in body_lines:
        if ':' in line:
            k, v = line.split(':', 1)
            parsed[k.strip()] = v.strip()

    # Determine merchant
    merchant = parsed.get('Пункт обслуживания') or parsed.get('Место') or parsed.get('Получатель')
    if not merchant:
        if len(body_lines) >= 3:
            merchant = body_lines[-3]
        elif body_lines:
            merchant = body_lines[-1]
        else:
            merchant = ''
    parsed['merchant'] = merchant

    return parsed


def fetch_new_transactions():
    """Fetch unread transaction emails and extract expense/income rows."""
    gmail_user = os.getenv('GMAIL_USER')
    app_pass = os.getenv('APP_PASS')
    sender = os.getenv('ALFA_SENDER_EMAIL', 'click@alfa-bank.by')

    logger.info("Fetching latest messages...")
    with EmailClient(gmail_user, app_pass, from_=sender) as client:
        messages = client.fetch_unread()
        if not messages:
            logger.info("No new messages found.")
            return [], []

        expenses_to_append = []
        income_to_append = []
        for message in messages:
            subject = message.get('subject') or ''
            logger.info(f"Processing: {subject}")
            try:
                extracted = parse_with_own_brains(message)
                if not (extracted and extracted.get('success')):
                    continue

                raw_sum = extracted.get('Сумма')
                amount, currency = parse_amount_and_currency(raw_sum)
                row = [
                    extracted.get('date', ''),
                    amount,
                    currency,
                    '',
                    extracted.get('merchant', '')
                ]

                if 'Поступление' in subject:
                    income_to_append.append(row)
                else:
                    expenses_to_append.append(row)
            except Exception as e:
                logger.error(f"Error processing message '{subject}': {e}", exc_info=True)

        return expenses_to_append, income_to_append

def append_to_sheet_safely(sheets_service, expenses_to_append, income_to_append):
    """Safely append transactions to the expenses and income sheets."""
    if expenses_to_append:
        append_rows(sheets_service, "expenses", expenses_to_append)
    if income_to_append:
        append_rows(sheets_service, "income", income_to_append)
    logger.info("Sync complete.")


def main():
    logger.info("Starting Gmail to Sheets Sync Service...")

    for var in ['GMAIL_USER', 'APP_PASS', 'SPREADSHEET_ID', 'CRED_FILE']:
        if not os.getenv(var):
            logger.error(f"Missing required environment variable: {var}")
            sys.exit(1)

    logger.info("Initializing Google Sheets API client...")
    try:
        sheets_service = init_sheets_service()
    except Exception as e:
        logger.error(f"Critical initialization error: {e}", exc_info=True)
        return

    # Start Telegram Bot in background thread if configured
    bot, bot_thread = start_bot_thread(sheets_service)

    poll_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "600"))

    while running:
        try:
            expenses_to_append, income_to_append = fetch_new_transactions()
            if expenses_to_append or income_to_append:
                append_to_sheet_safely(
                    sheets_service=sheets_service,
                    expenses_to_append=expenses_to_append,
                    income_to_append=income_to_append
                )
        except Exception as e:
            logger.error(f"Service error: {e}", exc_info=True)

        logger.info(f"Sleeping for {poll_interval} seconds...")
        for _ in range(poll_interval):
            if not running:
                break
            time.sleep(1)

    if bot:
        logger.info("Stopping Telegram bot...")
        try:
            bot.stop_polling()
        except Exception as e:
            logger.warning(f"Error stopping Telegram bot: {e}")

    logger.info("Service shut down cleanly.")


if __name__ == '__main__':
    main()
