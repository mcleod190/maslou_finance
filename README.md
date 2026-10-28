# Maslou Finance

A personal finance tracker that automatically parses transaction email notifications (from Alfa-Bank) into Google Sheets and provides an interactive Telegram bot for manual expense tracking and monthly spending summaries.

---

## Getting Started

### 1. Prerequisites & Account Setup

#### A. Gmail IMAP Configuration & App Password
To allow the script to fetch transaction emails from Gmail via IMAP:

1. **Enable IMAP in Gmail:**
   - Open [Gmail](https://mail.google.com/) in your browser.
   - Click the gear icon in the top-right corner and select **See all settings**.
   - Go to the **Forwarding and POP/IMAP** tab.
   - Under the **IMAP access** section, choose **Enable IMAP**.
   - Click **Save Changes** at the bottom of the page.

2. **Generate a Google App Password (Required):**
   - Standard Gmail passwords cannot be used directly with IMAP when 2-Step Verification is active.
   - Go to your [Google Account Security settings](https://myaccount.google.com/security).
   - Ensure **2-Step Verification** is turned ON.
   - Under the **How you sign in to Google** section, navigate to **App passwords** (or visit `https://myaccount.google.com/apppasswords` directly).
   - Give the app a name (e.g., `Maslou Finance`) and click **Create**.
   - Copy the generated 16-character passcode (e.g., `abcd efgh ijkl mnop`).
   - In your `.env` file, set:
     ```env
     GMAIL_USER="your_email@gmail.com"
     APP_PASS="abcdefghijklmnop"
     ```

3. **Bank Notifications:**
   - Ensure email transaction notifications (Alfa-Check / e-mail alerts) are activated in your bank account, sending notifications from `click@alfa-bank.by`.

---

#### B. Google Sheets & Cloud API
1. **Google Cloud Console:**
   - Go to the [Google Cloud Console](https://console.cloud.google.com/).
   - Create a project (or select an existing one).
   - Enable the **Google Sheets API** under **APIs & Services > Library**.
   - Go to **APIs & Services > Credentials** and create a **Service Account**.
   - Click the newly created service account, go to the **Keys** tab, select **Add Key > Create new key > JSON**, and download the file.
   - Place this file in the `secrets/` directory (e.g., `secrets/service-account.json`).
   - Set `CRED_FILE="service-account.json"` in your `.env`.

2. **Google Spreadsheet:**
   - Create a Google Sheet with two sheets (tabs): `expenses` and `income`.
   - Copy the spreadsheet ID from the URL (`https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit`).
   - Set `SPREADSHEET_ID="<SPREADSHEET_ID>"` in your `.env`.
   - **Important:** Share the spreadsheet with the service account's email address (found in the JSON file) with **Editor** permissions.

---

#### C. Telegram Bot Setup (How to Create a Bot & Get its Secret Token)

1. **Open BotFather:**
   - Open Telegram and search for the official [@BotFather](https://t.me/BotFather) bot (verified checkmark).
   - Press **Start** or send `/start`.

2. **Create a New Bot:**
   - Send the `/newbot` command.
   - Enter a display name for your bot (e.g., `My Finance Tracker`).
   - Enter a unique username for your bot that ends with `bot` (e.g., `my_finance_tracker_bot`).

3. **Copy the Bot Secret Token:**
   - BotFather will reply with a confirmation message containing your API token (looks like `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz_1234567`).
   - Copy this token and paste it into your `.env` file:
     ```env
     TELEGRAM_BOT_TOKEN="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz_1234567"
     ```
   - ⚠️ *Keep this token secret — anyone with the token can control your bot.*

4. **Find Your Telegram User ID (For Whitelisting):**
   - To make sure strangers cannot record transactions or view your financial summaries, restrict the bot to your account.
   - Search for [@userinfobot](https://t.me/userinfobot) or [@raw_data_bot](https://t.me/raw_data_bot) on Telegram and start it.
   - Copy your numeric `Id` (e.g., `123456789`).
   - Add it to `.env`:
     ```env
     ALLOWED_TELEGRAM_USER_IDS="123456789"
     ```
   - (If multiple people in your household need access, separate IDs with commas: `"123456789,987654321"`).

---

### 2. Environment Variables (`.env`)

Copy `.env_sample` to `.env` and fill in your values:

```shell
cp .env_sample .env
```

```env
# Google Sheet ID
SPREADSHEET_ID="your_google_sheet_id_here"

# Service Account credentials file inside ./secrets/
CRED_FILE="your_service_account_credentials.json"

# Gmail IMAP Credentials
GMAIL_USER="your_email@gmail.com"
APP_PASS="your_16_character_app_password"

# Telegram Bot configuration
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
ALLOWED_TELEGRAM_USER_IDS="12345678"
DEFAULT_CURRENCY="BYN"
```

---

### 3. Installation

Clone the repository and set up a Python virtual environment:

```shell
git clone https://github.com/mcleod190/maslou_finance.git
cd maslou_finance

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

### 4. Running the Service

#### Option A: Run directly in background
```shell
nohup python3 -u main.py > nohup.out 2>&1 &
```

#### Option B: Docker Compose
```shell
docker compose up -d
```

---

### 5. Telegram Bot Commands

| Command | Description | Example |
|---|---|---|
| `/add <сумма> <категория> [описание]` | Add a manual expense row to Google Sheets | `/add 15 кафе обед` |
| `/summary` | View current month's total spending grouped by category | `/summary` |
| `/help` | View help and usage instructions | `/help` |
