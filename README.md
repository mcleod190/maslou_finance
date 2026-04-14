# Maslou finance
The script will track email notifications about transactions from alfa-babk and add to list of transactions in google spreadsheet

## Getting Started

### Prerequisite
* First you need to enable notifications about transaction to email (alfa-check, like sms)
* Enable POP/IMAP in your gmail settings
* Open google sheet for transactions and copy ID from url -> paste into .env SPREADSHEET_ID
* Go to google console and activate API for google sheets
* Download credentials file and put it into secrets folder of thie project
* Paste the name of the secret file into .env CRED_FILE

### Installing
* clode repo
* activate virtual env
* install dependencies from requirements.txt

### Running

Run in background as simple as that
```shell
nohup python3 -u main.py &
```