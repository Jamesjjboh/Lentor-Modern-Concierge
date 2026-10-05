"""Unit tests for Estate Contacts Hub interactive menus."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import InlineKeyboardMarkup

from src.bot import (
    get_contacts_hub_keyboard,
    get_back_to_contacts_keyboard,
    handle_contacts_callback,
    handle_quick_menu_callback,
)


class TestContactsHub(unittest.IsolatedAsyncioTestCase):
    def test_contacts_hub_keyboard_structure(self):
        kb = get_contacts_hub_keyboard()
        self.assertIsInstance(kb, InlineKeyboardMarkup)
        self.assertEqual(len(kb.inline_keyboard), 4)

        # Row 1: Appliances & Equipment
        self.assertEqual(kb.inline_keyboard[0][0].callback_data, "contacts_appliances")
        self.assertIn("Appliances", kb.inline_keyboard[0][0].text)

        # Row 2: Fittings & Utilities
        self.assertEqual(kb.inline_keyboard[1][0].callback_data, "contacts_fittings")
        self.assertEqual(kb.inline_keyboard[1][1].callback_data, "contacts_utilities")

        # Row 3: Draft Email to MA
        self.assertEqual(kb.inline_keyboard[2][0].callback_data, "contacts_draft_ma")

        # Row 4: Back to Quick Menu
        self.assertEqual(kb.inline_keyboard[3][0].callback_data, "menu_main")

    def test_back_to_contacts_keyboard(self):
        kb = get_back_to_contacts_keyboard()
        self.assertIsInstance(kb, InlineKeyboardMarkup)
        self.assertEqual(len(kb.inline_keyboard), 1)
        self.assertEqual(kb.inline_keyboard[0][0].callback_data, "menu_contacts")
        self.assertEqual(kb.inline_keyboard[0][1].callback_data, "menu_main")

    async def test_handle_contacts_appliances_callback(self):
        update = MagicMock()
        context = MagicMock()
        query = AsyncMock()
        query.data = "contacts_appliances"
        query.from_user.first_name = "Alice"
        update.callback_query = query

        await handle_contacts_callback(update, context)

        query.answer.assert_awaited_once()
        query.edit_message_text.assert_awaited_once()
        call_kwargs = query.edit_message_text.call_args[1]
        text = call_kwargs["text"]
        self.assertIn("Mitsubishi Electric", text)
        self.assertIn("6473 2308", text)
        self.assertIn("SMEG", text)
        self.assertIn("Assa Abloy (Yale)", text)
        self.assertIn("6591 8868", text)
        self.assertIn("Rheem", text)
        self.assertIn("Fermax", text)

    async def test_handle_contacts_fittings_callback(self):
        update = MagicMock()
        context = MagicMock()
        query = AsyncMock()
        query.data = "contacts_fittings"
        query.from_user.first_name = "Alice"
        update.callback_query = query

        await handle_contacts_callback(update, context)

        query.answer.assert_awaited_once()
        query.edit_message_text.assert_awaited_once()
        call_kwargs = query.edit_message_text.call_args[1]
        text = call_kwargs["text"]
        self.assertIn("Hungsen Engineering", text)
        self.assertIn("6339 2131", text)
        self.assertIn("PD Door", text)
        self.assertIn("Carera Bathroom", text)
        self.assertIn("Jin Yuan Engineering", text)
        self.assertIn("Lian Beng Construction", text)

    async def test_handle_contacts_utilities_callback(self):
        update = MagicMock()
        context = MagicMock()
        query = AsyncMock()
        query.data = "contacts_utilities"
        query.from_user.first_name = "Alice"
        update.callback_query = query

        await handle_contacts_callback(update, context)

        query.answer.assert_awaited_once()
        query.edit_message_text.assert_awaited_once()
        call_kwargs = query.edit_message_text.call_args[1]
        text = call_kwargs["text"]
        self.assertIn("SP Services", text)
        self.assertIn("1800-222-2333", text)
        self.assertIn("City Energy", text)
        self.assertIn("1800-555-1661", text)

    async def test_handle_contacts_draft_ma_callback(self):
        update = MagicMock()
        context = MagicMock()
        query = AsyncMock()
        query.data = "contacts_draft_ma"
        query.from_user.first_name = "Ken"
        update.callback_query = query

        await handle_contacts_callback(update, context)

        query.answer.assert_awaited_once()
        query.edit_message_text.assert_awaited_once()
        call_kwargs = query.edit_message_text.call_args[1]
        text = call_kwargs["text"]
        self.assertIn("managementoffice@LT-MODERN.COM", text)
        self.assertIn("Ken", text)

    async def test_quick_menu_contacts_opens_hub(self):
        update = MagicMock()
        context = MagicMock()
        query = AsyncMock()
        query.data = "menu_contacts"
        query.from_user.id = 12345
        update.callback_query = query

        with patch("src.bot.db_client"):
            await handle_quick_menu_callback(update, context)

        query.answer.assert_awaited_once()
        query.edit_message_text.assert_awaited_once()
        call_kwargs = query.edit_message_text.call_args[1]
        self.assertIn("Primary On-Site Estate Contacts", call_kwargs["text"])
        reply_markup = call_kwargs["reply_markup"]
        self.assertIsInstance(reply_markup, InlineKeyboardMarkup)
        # Check that contacts hub buttons are attached
        callbacks = [btn.callback_data for row in reply_markup.inline_keyboard for btn in row]
        self.assertIn("contacts_appliances", callbacks)
        self.assertIn("contacts_fittings", callbacks)
        self.assertIn("contacts_utilities", callbacks)
        self.assertIn("contacts_draft_ma", callbacks)


if __name__ == "__main__":
    unittest.main()
