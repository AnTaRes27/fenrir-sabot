#!/usr/bin/env python

"""
Fenrir Sabot
"""

from __future__ import annotations

import logging
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


# config class
class Config:
    def __init__(self, config_filename: str) -> None:
        self.config_filename = config_filename
        try:
            self.config = yaml.safe_load(open(self.config_filename))
        except FileNotFoundError:
            logger.warning("No config file found! Creating one..")
            shutil.copyfile("default_config.yaml", self.config_filename)
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
        self.SLOT_MACHINE_VALUE = {
            1: ("bar", "bar", "bar"),
            2: ("grape", "bar", "bar"),
            3: ("lemon", "bar", "bar"),
            4: ("seven", "bar", "bar"),
            5: ("bar", "grape", "bar"),
            6: ("grape", "grape", "bar"),
            7: ("lemon", "grape", "bar"),
            8: ("seven", "grape", "bar"),
            9: ("bar", "lemon", "bar"),
            10: ("grape", "lemon", "bar"),
            11: ("lemon", "lemon", "bar"),
            12: ("seven", "lemon", "bar"),
            13: ("bar", "seven", "bar"),
            14: ("grape", "seven", "bar"),
            15: ("lemon", "seven", "bar"),
            16: ("seven", "seven", "bar"),
            17: ("bar", "bar", "grape"),
            18: ("grape", "bar", "grape"),
            19: ("lemon", "bar", "grape"),
            20: ("seven", "bar", "grape"),
            21: ("bar", "grape", "grape"),
            22: ("grape", "grape", "grape"),
            23: ("lemon", "grape", "grape"),
            24: ("seven", "grape", "grape"),
            25: ("bar", "lemon", "grape"),
            26: ("grape", "lemon", "grape"),
            27: ("lemon", "lemon", "grape"),
            28: ("seven", "lemon", "grape"),
            29: ("bar", "seven", "grape"),
            30: ("grape", "seven", "grape"),
            31: ("lemon", "seven", "grape"),
            32: ("seven", "seven", "grape"),
            33: ("bar", "bar", "lemon"),
            34: ("grape", "bar", "lemon"),
            35: ("lemon", "bar", "lemon"),
            36: ("seven", "bar", "lemon"),
            37: ("bar", "grape", "lemon"),
            38: ("grape", "grape", "lemon"),
            39: ("lemon", "grape", "lemon"),
            40: ("seven", "grape", "lemon"),
            41: ("bar", "lemon", "lemon"),
            42: ("grape", "lemon", "lemon"),
            43: ("lemon", "lemon", "lemon"),
            44: ("seven", "lemon", "lemon"),
            45: ("bar", "seven", "lemon"),
            46: ("grape", "seven", "lemon"),
            47: ("lemon", "seven", "lemon"),
            48: ("seven", "seven", "lemon"),
            49: ("bar", "bar", "seven"),
            50: ("grape", "bar", "seven"),
            51: ("lemon", "bar", "seven"),
            52: ("seven", "bar", "seven"),
            53: ("bar", "grape", "seven"),
            54: ("grape", "grape", "seven"),
            55: ("lemon", "grape", "seven"),
            56: ("seven", "grape", "seven"),
            57: ("bar", "lemon", "seven"),
            58: ("grape", "lemon", "seven"),
            59: ("lemon", "lemon", "seven"),
            60: ("seven", "lemon", "seven"),
            61: ("bar", "seven", "seven"),
            62: ("grape", "seven", "seven"),
            63: ("lemon", "seven", "seven"),
            64: ("seven", "seven", "seven"),
        }

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

    def update_tally(self, id: int, tally: list) -> None:
        with sqlite3.connect(self.db_filename) as connection:
            cursor = connection.cursor()
            q_update_tally = """
                UPDATE Gambler_tally SET tally = ? WHERE id = ?;
            """
            cursor.execute(q_update_tally, (json.dumps(tally), id))
            connection.commit()

    def update_balance(self, id: int, balance: int) -> None:
        with sqlite3.connect(self.db_filename) as connection:
            cursor = connection.cursor()
            q_update_tally = """
                UPDATE Gambler_tally SET balance_cents = ? WHERE id = ?;
            """
            cursor.execute(q_update_tally, (balance, id))
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
    message = f"""
@{username}'s Performance
Total Plays: {total_plays}

Wins:
7️⃣7️⃣7️⃣: {data["tally"][64-1]}
◼️◼️◼️: {data["tally"][1-1]}
🍋🍋🍋: {data["tally"][43-1]}
🍇🍇🍇: {data["tally"][22-1]}

Balance: {"" if data["balance_cents"]>=0 else "-"}${abs(data["balance_cents"])/100:.2f}
"""
    await update.message.reply_text(message)


@command_handler("paytable")
async def paytable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = """
Payout:
7️⃣7️⃣7️⃣: $20.00
◼️◼️◼️: $10.00
🍋🍋🍋/🍇🍇🍇: $2.50
Any Two ◼️: $0.25

Bet Amount = $0.25
"""
    await update.message.reply_text(message)


@command_handler("leaderboard")
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pass


@command_handler("redeem")
async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pass


@message_handler(filters.Dice.SLOT_MACHINE & ~filters.FORWARDED)
async def slot_machine_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    # logger.info(update.message.dice)
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
    match value:
        case 64:
            balance_add = 2000
        case 1:
            balance_add = 1000
        case 43 | 22:
            balance_add = 250
        case 22:
            balance_add = 250
        case 2 | 3 | 4 | 5 | 9 | 13 | 17 | 33 | 49:
            balance_add = 25
        case _:
            balance_add = -25
    balance += balance_add
    gambler_info_handler.update_balance(id, balance)

    logger.info(
        f"""{name}({id}) - {update.message.dice} - Total Game: {sum(tally)} - Balance: {"" if balance>=0 else "-"}$ {abs(balance)/100:.2f}"""
    )

    if value == 64:
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
