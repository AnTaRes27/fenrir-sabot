#!/usr/bin/env python

"""
Fenrir Sabot
"""

from __future__ import annotations

import logging
import os
import sys

import sqlite3
import shutil
import yaml
import json
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - [%(levelname)s] %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

EMOJI = {"seven": "7️⃣", "bar": "◼️", "lemon": "🍋", "grape": "🍇"}


# config class
class Config:
    def __init__(self, config_filename: str) -> None:
        location = os.path.realpath(
            os.path.join(os.getcwd(), os.path.dirname(__file__))
        )
        self.config_filename = config_filename
        try:
            self.config = yaml.safe_load(open(os.path.join(location, config_filename)))
        except FileNotFoundError:
            logger.warning("No config file found! Creating one..")
            shutil.copyfile(
                os.path.join(location, "default_config.yaml"), config_filename
            )
            logger.warning(
                f"Insert your API key in {self.config_filename} and rerun program."
            )
            sys.exit()

        self.db_filename = self.config["database"]["filename"]
        self.token = self.config["bot"]["token"]


config = Config("config.yaml")


# gambler info handler class
class GamblerInfoHandler:
    def __init__(self, db_filename: str) -> None:
        self.db_filename = db_filename
        with sqlite3.connect(self.db_filename) as connection:
            cursor = connection.cursor()
            q_create_table = """
            CREATE TABLE IF NOT EXISTS Gambler_Tally (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                tally TEXT NOT NULL,
                balance_cents INTEGER NOT NULL
            );
            """
            cursor.execute(q_create_table)
            connection.commit()
        self.setup_slot_machine_values()

    def setup_slot_machine_values(self):
        """Set up slot machine values with meaningful lookups."""
        symbols = ["bar", "grape", "lemon", "seven"]
        self.SLOT_MACHINE_VALUE = {}
        self.COMBINATIONS = {}

        # Generate all combinations
        index = 1
        for first in symbols:
            for second in symbols:
                for third in symbols:
                    self.SLOT_MACHINE_VALUE[index] = (first, second, third)

                    # Store reverse mapping for lookup
                    combo_key = f"{first}_{second}_{third}"
                    self.COMBINATIONS[combo_key] = index

                    index += 1

        self.TRIPLE_SEVEN = self.COMBINATIONS["seven_seven_seven"]
        self.TRIPLE_BAR = self.COMBINATIONS["bar_bar_bar"]
        self.TRIPLE_LEMON = self.COMBINATIONS["lemon_lemon_lemon"]
        self.TRIPLE_GRAPE = self.COMBINATIONS["grape_grape_grape"]

        # Double bar combinations
        self.DOUBLE_BAR_COMBOS = (
            [
                self.COMBINATIONS[f"bar_bar_{symbol}"]
                for symbol in symbols
                if symbol != "bar"
            ]
            + [
                self.COMBINATIONS[f"bar_{symbol}_bar"]
                for symbol in symbols
                if symbol != "bar"
            ]
            + [
                self.COMBINATIONS[f"{symbol}_bar_bar"]
                for symbol in symbols
                if symbol != "bar"
            ]
        )

    def get_combo_name(self, value: int) -> str:
        """Return a human-readable name for a slot combination."""
        if value == self.TRIPLE_SEVEN:
            return "Triple Seven"
        elif value == self.TRIPLE_BAR:
            return "Triple Bar"
        elif value == self.TRIPLE_LEMON:
            return "Triple Lemon"
        elif value == self.TRIPLE_GRAPE:
            return "Triple Grape"
        elif value in self.DOUBLE_BAR_COMBOS:
            return "Double Bar"
        else:
            symbols = self.SLOT_MACHINE_VALUE[value]
            return f"{symbols[0].capitalize()}-{symbols[1].capitalize()}-{symbols[2].capitalize()}"

    def init_data(self, id: int, name: str) -> dict[int, str, list, int]:
        # telegram's slot machine is a 1-64 RNG, each number corresponds to a 3 slot combo
        tally = []
        for x in range(64):
            tally.append(0)
        tally_json = json.dumps(tally)

        # store money as cents, makes more cents than real ahahahaaaa
        balance_cents = 0

        with sqlite3.connect(self.db_filename) as connection:
            cursor = connection.cursor()

            q_add_entry = """
            INSERT INTO Gambler_Tally (id, name, tally, balance_cents)
            VALUES (?, ?, ?, ?);
            """
            entry_data = (id, name, tally_json, balance_cents)

            cursor.execute(q_add_entry, entry_data)
            connection.commit()
        return {
            "id": id,
            "name": name,
            "tally": json.loads(tally_json),
            "balance_cents": balance_cents,
        }

    def get_data(self, id: int, name: str) -> dict[int, str, list, int]:
        with sqlite3.connect(self.db_filename) as connection:
            cursor = connection.cursor()
            q_get_user = """
                SELECT id, name, tally, balance_cents FROM Gambler_Tally WHERE id=?;
            """
            cursor.execute(q_get_user, (id,))
            data = cursor.fetchone()
            if data is None:
                return self.init_data(id, name)
            else:
                return {
                    "id": data[0],
                    "name": data[1],
                    "tally": json.loads(data[2]),
                    "balance_cents": data[3],
                }

    def get_leaderboard(self, limit: int) -> list[dict[int, str, list, int]]:
        with sqlite3.connect(self.db_filename) as connection:
            cursor = connection.cursor()
            q_get_topX = """
                SELECT id, name, tally, balance_cents FROM Gambler_Tally ORDER BY balance_cents DESC LIMIT ?;
            """
            cursor.execute(q_get_topX, (limit,))
            data = cursor.fetchall()

            if not data:
                return []

            return [
                {
                    "id": user[0],
                    "name": user[1],
                    "tally": json.loads(user[2]),
                    "balance_cents": user[3],
                }
                for user in data
            ]

    def get_user_rank(self, id: int) -> int:
        with sqlite3.connect(self.db_filename) as connection:
            cursor = connection.cursor()

            q_get_balance = """
                SELECT balance_cents FROM Gambler_Tally WHERE id = ?;
            """
            cursor.execute(q_get_balance, (id,))
            balance_result = cursor.fetchone()

            if balance_result is None:
                return 0  # User not found

            balance = balance_result[0]

            q_get_rank = """
                SELECT COUNT(*) FROM Gambler_Tally WHERE balance_cents > ?;
            """
            cursor.execute(q_get_rank, (balance,))
            rank_above = cursor.fetchone()[0]

            return rank_above + 1

    def update_tally(self, id: int, tally: list) -> None:
        with sqlite3.connect(self.db_filename) as connection:
            cursor = connection.cursor()
            q_update_tally = """
                UPDATE Gambler_Tally SET tally = ? WHERE id = ?;
            """
            cursor.execute(q_update_tally, (json.dumps(tally), id))
            connection.commit()

    def update_balance(self, id: int, balance: int) -> None:
        with sqlite3.connect(self.db_filename) as connection:
            cursor = connection.cursor()
            q_update_balance = """
                UPDATE Gambler_Tally SET balance_cents = ? WHERE id = ?;
            """
            cursor.execute(q_update_balance, (balance, id))
            connection.commit()


gambler_info_handler = GamblerInfoHandler(config.db_filename)

# bot definitions
app = ApplicationBuilder().token(config.token).build()


def command_handler(command: str):
    def decorator(func):
        handler = CommandHandler(command, func)
        app.add_handler(handler)
        return func

    return decorator


def message_handler(filters: filters) -> callable[[callable], callable]:
    def decorator(func: callable[[Update, ContextTypes.DEFAULT_TYPE], None]):
        handler = MessageHandler(filters, func)
        app.add_handler(handler)
        return func

    return decorator


@command_handler("stat")
async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    id = update.message.from_user.id
    name = update.message.from_user.full_name
    username = update.message.from_user.username
    reply_to_message_obj = update.message.reply_to_message

    if reply_to_message_obj is not None:
        reply_to_user_id = reply_to_message_obj.from_user.id
        reply_to_user_name = reply_to_message_obj.from_user.full_name
        username = reply_to_message_obj.from_user.username
        data = gambler_info_handler.get_data(reply_to_user_id, reply_to_user_name)
    else:
        data = gambler_info_handler.get_data(id, name)

    logger.info(f"stat call: {data}")
    total_plays = sum(data["tally"])

    # Handle case where username might be None
    display_name = f"@{username}" if username else name

    triple_seven = (
        gambler_info_handler.TRIPLE_SEVEN - 1
    )  # Adjust for 0-indexing in tally
    triple_bar = gambler_info_handler.TRIPLE_BAR - 1
    triple_lemon = gambler_info_handler.TRIPLE_LEMON - 1
    triple_grape = gambler_info_handler.TRIPLE_GRAPE - 1

    message = f"""
{display_name}'s Performance 
Total Plays: {total_plays}

Wins:
{EMOJI["seven"]}{EMOJI["seven"]}{EMOJI["seven"]}: {data["tally"][triple_seven]}
{EMOJI["bar"]}{EMOJI["bar"]}{EMOJI["bar"]}: {data["tally"][triple_bar]}
{EMOJI["lemon"]}{EMOJI["lemon"]}{EMOJI["lemon"]}: {data["tally"][triple_lemon]}
{EMOJI["grape"]}{EMOJI["grape"]}{EMOJI["grape"]}: {data["tally"][triple_grape]}

Balance: {"" if data["balance_cents"]>=0 else "-"}${abs(data["balance_cents"])/100:.2f}
"""
    await update.message.reply_text(message)


@command_handler("paytable")
async def paytable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = f"""
Payout:
{EMOJI["seven"]}{EMOJI["seven"]}{EMOJI["seven"]}: $20.00
{EMOJI["bar"]}{EMOJI["bar"]}{EMOJI["bar"]}: $10.00
{EMOJI["lemon"]}{EMOJI["lemon"]}{EMOJI["lemon"]}/{EMOJI["grape"]}{EMOJI["grape"]}{EMOJI["grape"]}: $2.50
Any Two {EMOJI["bar"]}: $0.25

Bet Amount = $0.25
"""
    await update.message.reply_text(message)


@command_handler("leaderboard")
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user_id = update.message.from_user.id
    current_user_name = update.message.from_user.full_name

    top_users = gambler_info_handler.get_leaderboard(10)

    top_users = [user for user in top_users if sum(user["tally"]) > 0]

    if not top_users:
        await update.message.reply_text(
            "No gambling has taken place yet... Be the first to win big! 🎰"
        )
        return

    current_user_in_top = any(user["id"] == current_user_id for user in top_users)

    current_user_data = gambler_info_handler.get_data(
        current_user_id, current_user_name
    )
    current_user_rank = gambler_info_handler.get_user_rank(current_user_id)
    has_played = sum(current_user_data["tally"]) > 0

    message = "🎰 Gambling Leaderboard 🎰\n\n"

    for i, user in enumerate(top_users):
        rank = i + 1
        balance = user["balance_cents"] / 100
        balance_str = f"{'$' if balance >= 0 else '-$'}{abs(balance):.2f}"

        user_indicator = " (You)" if user["id"] == current_user_id else ""

        message += f"{rank}. {user['name']}: {balance_str}{user_indicator}\n"

    if has_played and not current_user_in_top:
        message += "...\n"
        current_user_balance = current_user_data["balance_cents"] / 100
        balance_str = f"{'$' if current_user_balance >= 0 else '-$'}{abs(current_user_balance):.2f}"
        message += f"{current_user_rank}. {current_user_name}: {balance_str} (You)\n"
    elif not has_played:
        message += "\nYou haven't tried your luck yet... Send the 🎰 emoji to win big!"

    await update.message.reply_text(message)


@command_handler("redeem")
async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pass


@message_handler(filters.Dice.SLOT_MACHINE & ~filters.FORWARDED)
async def slot_machine_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    id = update.message.from_user.id
    name = update.message.from_user.full_name
    value = update.message.dice.value
    data = gambler_info_handler.get_data(id, name)

    # update tally
    tally = data["tally"]
    tally[value - 1] += 1
    gambler_info_handler.update_tally(id, tally)

    # update balance
    # remember they're in cents
    balance = data["balance_cents"]

    if value == gambler_info_handler.TRIPLE_SEVEN:
        balance_add = 2000
    elif value == gambler_info_handler.TRIPLE_BAR:
        balance_add = 1000
    elif (
        value == gambler_info_handler.TRIPLE_LEMON
        or value == gambler_info_handler.TRIPLE_GRAPE
    ):
        balance_add = 250
    elif value in gambler_info_handler.DOUBLE_BAR_COMBOS:
        balance_add = 25
    else:
        balance_add = -25

    balance += balance_add
    gambler_info_handler.update_balance(id, balance)

    combo_name = gambler_info_handler.get_combo_name(value)

    logger.info(
        f"""{name}({id}) - {combo_name} - Total Games: {sum(tally)} - Balance: {"" if balance>=0 else "-"}${abs(balance)/100:.2f}"""
    )

    if value == gambler_info_handler.TRIPLE_SEVEN:
        await update.message.reply_text("Ahoy!")


async def debugging(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """logs user message for debugging"""
    logger.info(update.message)
    # await update.message.reply_text(update.message.text)
    # logger.info(update.chat_member)
    # logger.info(update.message.chat.id)
    # logger.info(update.message.chat_id)
    # logger.info(update.message.text)
    # logger.info(update.message.chat)
    logger.info(update.message.from_user)
    # logger.info(update.message.dice)


def main() -> None:
    app.add_handler(MessageHandler(None, debugging))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
