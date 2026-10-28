import os
import re
import logging
from datetime import datetime
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

_sheets_service_instance = None


def get_sheets_service():
    """Singleton getter for Google Sheets API client."""
    global _sheets_service_instance
    if _sheets_service_instance is None:
        _sheets_service_instance = init_sheets_service()
    return _sheets_service_instance


def init_sheets_service():
    """Initialize and return Google Sheets API client."""
    cred_file_name = os.getenv('CRED_FILE')
    if not cred_file_name:
        raise ValueError("CRED_FILE is not set in environment.")

    secret_file = BASE_DIR / 'secrets' / cred_file_name
    if not secret_file.is_file():
        secret_file = Path('secrets') / cred_file_name
        if not secret_file.is_file():
            raise FileNotFoundError(f"Credentials file not found: {cred_file_name}")

    creds = service_account.Credentials.from_service_account_file(
        str(secret_file), scopes=SCOPES
    )
    return build('sheets', 'v4', credentials=creds, cache_discovery=False)


def append_rows(sheets_service, sheet_name: str, rows: list) -> bool:
    """Safely append multiple rows to {sheet_name}!A:E."""
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    if not spreadsheet_id:
        logger.error("SPREADSHEET_ID not found in environment variables")
        return False
    if not rows:
        return True

    logger.info(f"Appending {len(rows)} rows to sheet '{sheet_name}'...")
    sheets_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A:E",
        valueInputOption="USER_ENTERED",
        body={"values": rows}
    ).execute(num_retries=3)
    return True


def add_expense_row(
    sheets_service,
    amount: float | str,
    category: str,
    description: str = "",
    currency: str | None = None,
    date_str: str | None = None
) -> list:
    """
    Append a single manual expense row to the 'expenses' sheet.
    Returns the appended row [date, amount, currency, category, description].
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    if currency is None:
        currency = os.getenv("DEFAULT_CURRENCY", "BYN")

    # Format amount cleanly
    if isinstance(amount, (int, float)):
        amount_str = f"{amount:.2f}".rstrip('0').rstrip('.') if isinstance(amount, float) else str(amount)
    else:
        amount_str = str(amount).strip().replace(',', '.')

    row = [
        date_str,
        amount_str,
        currency.strip(),
        category.strip().capitalize(),
        description.strip()
    ]

    append_rows(sheets_service, "expenses", [row])
    return row


def get_monthly_expenses_summary(sheets_service, year: int | None = None, month: int | None = None) -> dict:
    """
    Fetch all rows from 'expenses!A:E', filter by year/month (default: current),
    and aggregate totals by category.
    """
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    if not spreadsheet_id:
        raise ValueError("SPREADSHEET_ID not set in environment.")

    now = datetime.now()
    target_year = year or now.year
    target_month = month or now.month
    month_prefix = f"{target_year:04d}-{target_month:02d}"

    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="expenses!A:E"
    ).execute(num_retries=3)

    rows = result.get('values', [])
    if not rows:
        return {
            'year': target_year,
            'month': target_month,
            'by_category': {},
            'currency': os.getenv('DEFAULT_CURRENCY', 'BYN'),
            'grand_total': 0.0,
            'transaction_count': 0
        }

    by_category: dict[str, float] = {}
    grand_total = 0.0
    count = 0
    detected_currency = os.getenv('DEFAULT_CURRENCY', 'BYN')

    for row in rows:
        if not row:
            continue

        row_date = str(row[0]).strip()
        # Check if row starts with the target month YYYY-MM
        if not row_date.startswith(month_prefix):
            continue

        raw_amount = row[1] if len(row) > 1 else ""
        raw_currency = row[2] if len(row) > 2 else ""
        raw_category = row[3] if len(row) > 3 else ""

        if raw_currency and raw_currency.strip():
            detected_currency = raw_currency.strip()

        # Parse amount
        cleaned_amount = re.sub(r'[^\d.,]', '', str(raw_amount)).replace(',', '.')
        try:
            amount_val = float(cleaned_amount)
        except (ValueError, TypeError):
            continue

        category = raw_category.strip().capitalize() if raw_category else "Без категории"
        by_category[category] = by_category.get(category, 0.0) + amount_val
        grand_total += amount_val
        count += 1

    return {
        'year': target_year,
        'month': target_month,
        'by_category': by_category,
        'currency': detected_currency,
        'grand_total': grand_total,
        'transaction_count': count
    }
