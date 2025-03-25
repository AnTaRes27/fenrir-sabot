#!/usr/bin/env python

"""
Message handlers for Telegram bot
"""

import logging
from typing import Any

from telegram import Update, constants
from telegram.ext import ContextTypes, filters, MessageHandler

from ..config import Config
from ..db.db_handler import DbHandler
from ..utils import parse_dollar_amount

logger = logging.getLogger(__name__)

# Set during initialization
db_handler = None
config = None

def init(app: Any, config_obj: Config, _db_handler: DbHandler):
    global config, db_handler

    config = config_obj
    db_handler = _db_handler

    register_message_handlers(app)

def register_message_handlers(app):
    app.add_handler(MessageHandler(filters.Dice.SLOT_MACHINE & ~filters.FORWARDED, slot_machine_handler))
    app.add_handler(MessageHandler(None, debugging))

async def slot_machine_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    id = update.message.from_user.id
    name = update.message.from_user.full_name
    username = update.message.from_user.username
    value = update.message.dice.value
    bet_cents = config.bet_cents

    # Process and get updated balance
    balance = db_handler.process_slot_machine(
        id, name, username, value, constants.DiceEmoji.SLOT_MACHINE, config.paytable, bet_cents
    )

    combo_name = db_handler.get_combo_name(value)
    data = db_handler.get_data(id, name, username)
    logger.info(
        f"""{name}({id}) - {combo_name} - Total Games: {sum(data["tally"])} - Balance: {parse_dollar_amount(balance)}"""
    )

    if value in (db_handler.TRIPLE_LEMON, db_handler.TRIPLE_GRAPE, db_handler.TRIPLE_BAR):
        await update.message.set_reaction("✨")
    elif value == db_handler.TRIPLE_SEVEN:
        await update.message.set_reaction("🔥")
        await update.message.reply_text("Ahoy!")

async def debugging(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """logs user message for debugging"""
    logger.info(update.message)
    logger.info(update.message.from_user)
