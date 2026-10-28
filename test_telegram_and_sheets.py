import os
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

from sheets_client import add_expense_row, get_monthly_expenses_summary
from telegram_bot import create_bot, get_allowed_user_ids, restricted


class TestSheetsClient(unittest.TestCase):
    def setUp(self):
        os.environ["SPREADSHEET_ID"] = "test_sheet_id"
        os.environ["DEFAULT_CURRENCY"] = "BYN"

    def test_add_expense_row(self):
        mock_sheets_service = MagicMock()
        mock_values = MagicMock()
        mock_sheets_service.spreadsheets.return_value.values.return_value = mock_values
        mock_values.append.return_value.execute.return_value = {}

        # Test with float and custom date
        row = add_expense_row(
            sheets_service=mock_sheets_service,
            amount=15.5,
            category="кафе",
            description="кофе с круассаном",
            currency="BYN",
            date_str="2026-10-28"
        )
        self.assertEqual(row, ["2026-10-28", "15.5", "BYN", "Кафе", "кофе с круассаном"])
        mock_values.append.assert_called_once()

    def test_get_monthly_expenses_summary(self):
        mock_sheets_service = MagicMock()
        mock_values = MagicMock()
        mock_sheets_service.spreadsheets.return_value.values.return_value = mock_values

        sample_rows = [
            ["Date", "Amount", "Currency", "Category", "Merchant"],  # Header
            ["2026-10-01", "100.00", "BYN", "продукты", "Евроопт"],
            ["2026-10-05", "25.50", "BYN", "кафе", "Кофейня"],
            ["2026-10-15", "50", "BYN", "Продукты", "Соседи"],
            ["2026-10-20", "30.00", "BYN", "", "Неизвестный перевод"],  # Empty category
            ["2026-09-25", "200.00", "BYN", "продукты", "Прошлый месяц"],  # Previous month
        ]
        mock_values.get.return_value.execute.return_value = {"values": sample_rows}

        summary = get_monthly_expenses_summary(mock_sheets_service, year=2026, month=10)
        self.assertEqual(summary["year"], 2026)
        self.assertEqual(summary["month"], 10)
        self.assertEqual(summary["transaction_count"], 4)
        self.assertAlmostEqual(summary["grand_total"], 205.50)
        self.assertAlmostEqual(summary["by_category"]["Продукты"], 150.00)
        self.assertAlmostEqual(summary["by_category"]["Кафе"], 25.50)
        self.assertAlmostEqual(summary["by_category"]["Без категории"], 30.00)
        self.assertNotIn("Прошлый месяц", str(summary))


class TestTelegramBot(unittest.TestCase):
    def setUp(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "123456:TEST_TOKEN"
        os.environ["ALLOWED_TELEGRAM_USER_IDS"] = "111,222"

    def test_get_allowed_user_ids(self):
        self.assertEqual(get_allowed_user_ids(), {111, 222})

    def test_restricted_decorator(self):
        func = MagicMock()
        wrapped = restricted(func)

        # Authorized user
        msg_auth = MagicMock()
        msg_auth.from_user.id = 111
        wrapped(msg_auth)
        func.assert_called_once_with(msg_auth)

        # Unauthorized user
        func.reset_mock()
        msg_unauth = MagicMock()
        msg_unauth.from_user.id = 999
        wrapped(msg_unauth)
        func.assert_not_called()

    @patch("sheets_client.append_rows")
    def test_bot_add_and_summary_handlers(self, mock_append):
        mock_sheets_service = MagicMock()
        bot = create_bot(mock_sheets_service)
        self.assertIsNotNone(bot)
        bot.reply_to = MagicMock()

        # Find handlers
        add_handler = next(h['function'] for h in bot.message_handlers if 'add' in h['filters'].get('commands', []))
        summary_handler = next(h['function'] for h in bot.message_handlers if 'summary' in h['filters'].get('commands', []))

        # Test /add 15 кафе
        msg_add = MagicMock()
        msg_add.from_user.id = 111
        msg_add.text = "/add 15 кафе"
        add_handler(msg_add)

        bot.reply_to.assert_called()
        self.assertIn("Расход записан", bot.reply_to.call_args[0][1])
        mock_append.assert_called_once()

        # Test /summary
        mock_values = MagicMock()
        mock_sheets_service.spreadsheets.return_value.values.return_value = mock_values
        mock_values.get.return_value.execute.return_value = {
            "values": [["2026-10-28", "15.00", "BYN", "кафе", ""]]
        }
        bot.reply_to.reset_mock()
        msg_summary = MagicMock()
        msg_summary.from_user.id = 111
        msg_summary.text = "/summary"
        summary_handler(msg_summary)

        bot.reply_to.assert_called()
        self.assertIn("Расходы за", bot.reply_to.call_args[0][1])
        self.assertIn("Кафе", bot.reply_to.call_args[0][1])


if __name__ == "__main__":
    unittest.main()

