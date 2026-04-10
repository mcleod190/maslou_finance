import os
import time
import json
import base64
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import google.generativeai as genai
import google_workspace
from dotenv import load_dotenv

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
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/gmail.modify'
]

def get_credentials():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def parse_with_own_brains(message):
    parsed = {'date': str(message.date.date())}
    parsed['success'] = 'Успешно' in message.text
    if not parsed['success']:
        logging.info("Unsuccessful transaction. Ignoring it..")
        return parsed
    parsed['merchant'] = message.text.split('\n')[-3]
    partial = dict((a.strip(), b.strip()) 
                   for a, b in  (element.split(':', maxsplit=1) 
                                 for element in message.text.split('\n') if ':' in element))
    parsed.update(partial)
    return parsed

def sync_gmail_to_sheets():
    creds = get_credentials()
    sheets_service = build('sheets', 'v4', credentials=creds)
    
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    if not spreadsheet_id:
        logger.error("SPREADSHEET_ID not found in environment variables")
        return

    logger.info("Fetching latest messages...")
    gmail_client = google_workspace.gmail.GmailClient()
    messages = list(gmail_client.get_messages(from_ = 'click@alfa-bank.by', seen=False))

    if not messages:
        logger.info("No new messages found.")
        return

    rows_to_append = []
    for message in messages:
        logger.info(f"Processing: {message.subject}")
        extracted = parse_with_own_brains(message)
        
        if extracted and extracted['success']:
            rows_to_append.append([
                extracted.get('date'),
                extracted.get('Сумма').split(' ')[0],
                extracted.get('Сумма').split(' ')[-1],
                '',
                extracted.get('merchant')
            ])
            message.mark_read()

    if rows_to_append:
        logger.info(f"Appending {len(rows_to_append)} rows to sheet...")
        sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="expenses!A:B",
            valueInputOption="USER_ENTERED",
            body={"values": rows_to_append}
        ).execute()
        logger.info("Sync complete.")

def extract_body(msg) -> str:
    if 'parts' in msg['payload']:
        for part in msg['payload']['parts']:
            if part['mimeType'] == 'text/plain':
                body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                break
    elif 'body' in msg['payload'] and 'data' in msg['payload']['body']:
        body = base64.urlsafe_b64decode(msg['payload']['body']['data']).decode('utf-8')
    return body

def main():
    logger.info("Starting Gmail to Sheets Sync Service...")
    while True:
        try:
            sync_gmail_to_sheets()
        except Exception as e:
            logger.error(f"Service error: {e}")
        
        # Wait for 10 minutes before next sync
        logger.info("Sleeping for 10 minutes...")
        time.sleep(600)

if __name__ == '__main__':
    main()
