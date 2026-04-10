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

def parse_with_gemini(subject, sender, date, body):
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
    Extract structured data from this email.
    Subject: {subject}
    From: {sender}
    Date: {date}
    Body: {body}

    Return a JSON object with these fields:
    - sender_name
    - sender_email
    - category (e.g. Invoice, Notification, Personal, Newsletter)
    - summary (one sentence)
    - amount (if applicable, else null)
    - date_received (ISO format)

    Only return the JSON.
    """
    
    try:
        response = model.generate_content(prompt)
        # Extract JSON from response text
        text = response.text
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != -1:
            return json.loads(text[start:end])
    except Exception as e:
        logger.error(f"Gemini parsing error: {e}")
    return None

def sync_gmail_to_sheets():
    creds = get_credentials()
    gmail_service = build('gmail', 'v1', credentials=creds)
    sheets_service = build('sheets', 'v4', credentials=creds)
    
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    if not spreadsheet_id:
        logger.error("SPREADSHEET_ID not found in environment variables")
        return

    logger.info("Fetching latest messages...")
    results = gmail_service.users().messages().list(userId='me', maxResults=10, q="is:unread").execute()
    messages = results.get('messages', [])

    if not messages:
        logger.info("No new messages found.")
        return

    rows_to_append = []
    for message in messages:
        msg = gmail_service.users().messages().get(userId='me', id=message['id']).execute()
        
        headers = msg['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
        sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
        date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
        
        # Simple body extraction
        body = ""
        body = extract_body(msg)

        logger.info(f"Processing: {subject}")
        extracted = parse_with_gemini(subject, sender, date, body)

        # Add a small delay to avoid hitting rate limits (429 errors)
        time.sleep(1)
        
        if extracted:
            rows_to_append.append([
                extracted.get('date_received', date),
                extracted.get('sender_name', sender),
                extracted.get('sender_email', ''),
                subject,
                extracted.get('category', 'Other'),
                extracted.get('summary', ''),
                extracted.get('amount', ''),
                message['id']
            ])
        else:
            rows_to_append.append([date, sender, '', subject, 'Error', 'Failed to parse', '', message['id']])

    if rows_to_append:
        logger.info(f"Appending {len(rows_to_append)} rows to sheet...")
        sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A2",
            valueInputOption="RAW",
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
