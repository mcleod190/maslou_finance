import os
import time
import logging
import socket
from googleapiclient.discovery import build
from google.oauth2 import service_account
from gmail_pop import EmailClient
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("service.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets'
]


orig_getaddrinfo = socket.getaddrinfo

def forced_ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

socket.getaddrinfo = forced_ipv4_getaddrinfo


def parse_with_own_brains(message):
    parsed = {'date': str(message.get('date').date())}
    parsed['success'] = 'Успешно' in message.get('body')
    if not parsed['success']:
        logging.info("Unsuccessful transaction. Ignoring it..")
        return parsed
    parsed['merchant'] = message.get('body').split('\n')[-3]
    partial = dict((a.strip(), b.strip()) 
                   for a, b in  (element.split(':', maxsplit=1) 
                                 for element in message.get('body').split('\n') if ':' in element))
    parsed.update(partial)
    return parsed


def fetch_new_transactions():
    logger.info("Fetching latest messages...")
    with EmailClient(os.getenv('GMAIL_USER'), os.getenv('APP_PASS'), from_='click@alfa-bank.by') as client:
        messages = client.fetch_unread()
        if not messages:
            logger.info("No new messages found.")
            return [], []

        expenses_to_append = []
        income_to_append = []
        for message in messages:
            logger.info(f"Processing: {message.get('subject')}")
            extracted = parse_with_own_brains(message)
            
            if extracted and extracted['success']:
                if 'Поступление' in message.get('subject'):
                    income_to_append.append([
                        extracted.get('date'),
                        extracted.get('Сумма').split(' ')[0],
                        extracted.get('Сумма').split(' ')[-1],
                        '',
                        extracted.get('merchant')
                    ])
                else:
                    expenses_to_append.append([
                        extracted.get('date'),
                        extracted.get('Сумма').split(' ')[0],
                        extracted.get('Сумма').split(' ')[-1],
                        '',
                        extracted.get('merchant')
                    ])
        return expenses_to_append, income_to_append

    
@retry(
    stop=stop_after_attempt(5), 
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
def append_to_sheet_safely(expenses_to_append, income_to_append):
    secret_file = os.path.join('./secrets', os.getenv('CRED_FILE'))
    creds = service_account.Credentials.from_service_account_file(
        secret_file, scopes=SCOPES)
    sheets_service = build('sheets', 'v4', credentials=creds, cache_discovery=False)
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    if not spreadsheet_id:
        logger.error("SPREADSHEET_ID not found in environment variables")
        return
    if expenses_to_append:
        logger.info(f"Appending {len(expenses_to_append)} rows to sheet...")
        sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="expenses!A:B",
            valueInputOption="USER_ENTERED",
            body={"values": expenses_to_append}
        ).execute(num_retries=2)

    if income_to_append:
        logger.info(f"Appending {len(income_to_append)} rows to sheet...")
        sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="income!A:B",
            valueInputOption="USER_ENTERED",
            body={"values": income_to_append}
        ).execute(num_retries=2)
        logger.info("Sync complete.")

def main():
    logger.info("Starting Gmail to Sheets Sync Service...")
    while True:
        try:
            expenses_to_append, income_to_append = fetch_new_transactions()
            if expenses_to_append or income_to_append:
                append_to_sheet_safely(expenses_to_append=expenses_to_append, income_to_append = income_to_append)
        except Exception as e:
            logger.error(f"Service error: {e}")
        
        # Wait for 10 minutes before next sync
        logger.info("Sleeping for 10 minutes...")
        time.sleep(600)

if __name__ == '__main__':
    main()
