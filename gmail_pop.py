import imaplib
from email import message_from_bytes
from email.header import decode_header
import datetime as dt


class EmailClient:
    """A simple email client supporting IMAP """
    
    def __init__(self, email, password, imap_server='imap.gmail.com', from_=None):
        self.email = email
        self.password = password
        self.imap_server = imap_server
        self.imap = None
        self.from_ = from_

    
    def connect_imap(self):
        """Establish pop connection"""
        self.imap = imaplib.IMAP4_SSL(self.imap_server)
        self.imap.login(self.email, self.password)
    
    def disconnect_imap(self):
        """Close pop connection"""
        if self.imap:
            try:
                self.imap.close()
            except Exception:
                pass
            try:
                self.imap.logout()
            except Exception:
                pass
    
    def fetch_unread(self, mailbox='INBOX', limit=10):
        """Fetch unread messages from specified mailbox"""
        if not self.imap:
            self.connect_imap()
        
        try:
            # Select the specific mailbox (folder)
            self.imap.select(mailbox)

            # Fetch unread email
            search_string = f'UNSEEN FROM "{self.from_}"' if self.from_ else "UNSEEN"
            status, search_data = self.imap.search(None, search_string)
            if status == 'OK':
                msg_id_list = search_data[0].split()[-limit:] #Get last N messages
                messages = []
                for msg_id in msg_id_list:
                    msg = self.fetch_email_details(msg_id)
                    messages.append(msg)
                return messages
         
        except Exception as e:
            print(f"Error: {e}")

        finally:
            self.disconnect_imap()

    def decode_email_header(self, header):
        """Decode email headers that may contain encoded content"""
        decoded_parts = decode_header(header)
        return ''.join([
            part.decode(encoding or 'utf-8') if isinstance(part, bytes) else part
            for part, encoding in decoded_parts
        ])
    
    def fetch_email_details(self, msg_id):
        """Fetch and parse a single email message"""
        _, msg_data = self.imap.fetch(msg_id, '(RFC822)')
        email_body = msg_data[0][1]
        email_message = message_from_bytes(email_body)
        
        # Extract metadata
        subject = self.decode_email_header(email_message['Subject'])
        from_addr = self.decode_email_header(email_message['From'])
        date = dt.datetime.strptime(email_message['Date'], '%d %b %Y %H:%M:%S %z')
        
        # Handle multipart messages
        body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    body = part.get_payload(decode=True).decode()
                    break
        else:
            body = email_message.get_payload(decode=True).decode()
        
        return {
            'subject': subject,
            'from': from_addr,
            'date': date,
            'body': body[:200]  # First 200 characters
        }

    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup connections"""
        self.disconnect_imap()