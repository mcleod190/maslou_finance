import poplib
import ssl
from email import parser


class EmailClient:
    """A simple email client supporting POP """
    
    def __init__(self, email, password, pop_server='pop.gmail.com'):
        self.email = email
        self.password = password
        self.pop_server = pop_server
        self.pop = None

    
    def connect_pop(self):
        """Establish pop connection"""
        context = ssl.create_default_context()
        self.pop = poplib.POP3_SSL(self.pop_server, 995, context=context)
        self.pop.user(self.email)
        self.pop.pass_(self.password)
        return self.pop
    
    def disconnect_pop(self):
        """Close pop connection"""
        if self.pop:
            self.pop.quit()
    
    def fetch_unread(self, mailbox='INBOX', limit=10):
        """Fetch unread messages from specified mailbox"""
        if not self.pop:
            self.connect_pop()
        
        try:
            # Get mailbox status
            messages, total_size = self.pop.stat()
            print(f"Total messages: {messages}")

            # Fetch top email
            if messages > 0:
                resp, lines, octets = self.pop.retr(messages)
                email_content = b'\n'.join(lines).decode('utf-8')
                msg = parser.BytesParser().parsebytes(b'\n'.join(lines))
                return msg
            
        except Exception as e:
            print(f"Error: {e}")

    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup connections"""
        self.disconnect_pop()