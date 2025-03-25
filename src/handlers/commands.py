#!/usr/bin/env python

"""
Command handlers for Telegram bot
"""

import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from ..config import Config
from ..models.paytable import SlotEmoji
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

    register_commands(app)


def register_commands(app):
    app.add_handler(CommandHandler("stat", stat))
    app.add_handler(CommandHandler("paytable", paytable))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("redeem", redeem))


async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    id = update.message.from_user.id
    name = update.message.from_user.full_name
    username = update.message.from_user.username
    reply_to_message_obj = update.message.reply_to_message

    # update name and username
    db_handler.update_user_data(id, name, username)

    if reply_to_message_obj is not None:
        reply_to_user_id = reply_to_message_obj.from_user.id
        reply_to_user_name = reply_to_message_obj.from_user.full_name
        reply_to_user_username = reply_to_message_obj.from_user.username
        username = reply_to_message_obj.from_user.username
        data = db_handler.get_data(
            reply_to_user_id, reply_to_user_name, reply_to_user_username
        )
    else:
        data = db_handler.get_data(id, name, username)

    logger.info(f"stat call: {data}")
    total_plays = sum(data["tally"])

    # Handle case where username might be None
    display_name = f"@{username}" if username else name

    triple_seven = db_handler.TRIPLE_SEVEN - 1  # Adjust for 0-indexing in tally
    triple_bar = db_handler.TRIPLE_BAR - 1
    triple_lemon = db_handler.TRIPLE_LEMON - 1
    triple_grape = db_handler.TRIPLE_GRAPE - 1

    message = f"""
{display_name}'s Performance 
Total Plays: {total_plays}

Wins:
{SlotEmoji.SEVEN.value*3}: {data["tally"][triple_seven]}
{SlotEmoji.BAR.value*3}: {data["tally"][triple_bar]}
{SlotEmoji.LEMON.value*3}: {data["tally"][triple_lemon]}
{SlotEmoji.GRAPE.value*3}: {data["tally"][triple_grape]}

Balance: {parse_dollar_amount(data["balance_cents"])}
"""
    await update.message.reply_text(message)


async def paytable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = config.paytable.to_display_string(config.bet_cents)
    await update.message.reply_text(message)


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user_id = update.message.from_user.id
    current_user_name = update.message.from_user.full_name
    current_user_username = update.message.from_user.username

    top_users = db_handler.get_leaderboard(10)

    top_users = [user for user in top_users if sum(user["tally"]) > 0]

    if not top_users:
        await update.message.reply_text(
            "No gambling has taken place yet... Be the first to win big! 🎰"
        )
        return

    current_user_in_top = any(user["id"] == current_user_id for user in top_users)

    current_user_data = db_handler.get_data(
        current_user_id, current_user_name, current_user_username
    )
    current_user_rank = db_handler.get_user_rank(current_user_id)
    has_played = sum(current_user_data["tally"]) > 0

    message = "🎰 Gambling Leaderboard 🎰\n\n"

    for i, user in enumerate(top_users):
        rank = i + 1
        balance = user["balance_cents"]
        balance_str = parse_dollar_amount(balance)
        user_indicator = " (You)" if user["id"] == current_user_id else ""
        message += f"{rank}. {user['name']}: {balance_str}{user_indicator}\n"

    if has_played and not current_user_in_top:
        message += "...\n"
        current_user_balance = current_user_data["balance_cents"]
        balance_str = parse_dollar_amount(current_user_balance)
        message += f"{current_user_rank}. {current_user_name}: {balance_str} (You)\n"
    elif not has_played:
        message += "\nYou haven't tried your luck yet... Send the 🎰 emoji to win big!"

    await update.message.reply_text(message)


async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Placeholder for redeem command
    pass
