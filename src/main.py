#!/usr/bin/env python

"""
Fenrir Sabot
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from enum import Enum
import json
from typing import List, Dict, Tuple, Any

import sqlite3
import shutil
import yaml
import json
from telegram import Update, Dice
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# process argument
argparser = argparse.ArgumentParser(description="FENRIR")
argparser.add_argument(
    "--config", default="config.yaml", type=str, help="Config filename"
)
args = argparser.parse_args()
config_filename = args.config


# enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - [%(levelname)s] %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class SlotEmoji(str, Enum):
    SEVEN = "7️⃣"
    BAR = "◼️"
    LEMON = "🍋"
    GRAPE = "🍇"
    ANY = ""

    @classmethod
    def from_value(cls, value: str) -> 'SlotEmoji':
        for emoji in cls:
            if emoji.value == value:
                return emoji
        return cls.ANY  # Default to ANY if not found

class PaytableEntry:
    """Structured class for paytable entries"""
    def __init__(self, combo: List[str], payout_mult: int):
        self.combo = [SlotEmoji.from_value(emoji) for emoji in combo]
        self.payout_mult = payout_mult
        
    def matches(self, slot_result: Tuple[str, str, str]) -> bool:
        if len(self.combo) != len(slot_result):
            return False
            
        for i, emoji in enumerate(self.combo):
            if emoji != SlotEmoji.ANY and emoji != slot_result[i]:
                return False
        return True
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "combo": [emoji.value for emoji in self.combo],
            "payout_mult": self.payout_mult
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PaytableEntry':
        return cls(data["combo"], data["payout_mult"])
        
    def __str__(self) -> str:
        emoji_str = ''.join([emoji.value if emoji != SlotEmoji.ANY else '*' for emoji in self.combo])
        return f"{emoji_str}: x{self.payout_mult}"

class Paytable:
    """Handles paytable operations and lookups"""
    def __init__(self, paytable_config: str):
        self.entries: List[PaytableEntry] = []
        self._load_from_config(paytable_config)
        
    def _load_from_config(self, paytable_config) -> None:
        """Load paytable from config"""
        if isinstance(paytable_config, list):
            if len(paytable_config) == 0:
                raise ValueError("Paytable is empty")
            paytable_data = paytable_config
        else:
            paytable_data = json.loads(paytable_config)

        self.entries = [PaytableEntry.from_dict(entry) for entry in paytable_data]

    def get_payout_multiplier(self, value: int, slot_mappings: Dict[int, Tuple[str, str, str]]) -> int:
        """Get the payout multiplier for a specific slot value"""
        if value not in slot_mappings:
            return 0

        slot_result = slot_mappings[value]
        slot_emojis = tuple(SlotEmoji[symbol.upper()].value for symbol in slot_result)

        for entry in self.entries:
            if entry.matches(slot_emojis):
                return entry.payout_mult

        return 0  # No match found
        
    def to_display_string(self, bet_cents: int) -> str:
        """Generate a readable paytable display"""
        message = "Payout:\n"
        
        for entry in self.entries:
            combo = entry.combo
            payout_amount = f"{entry.payout_mult * bet_cents / 100:.2f}"

            # Count non-ANY symbols for display logic
            non_any = [emoji for emoji in combo if emoji != SlotEmoji.ANY]
            any_count = combo.count(SlotEmoji.ANY)

            if any_count == 0:
                # All three symbols are the same
                emoji = non_any[0]
                message += f"{emoji*3}: x{entry.payout_mult} (${payout_amount})\n"
            elif any_count == 2 and len(non_any) == 1:
                # One symbol anywhere
                emoji = non_any[0]
                message += f"Any {emoji}: x{entry.payout_mult} (${payout_amount})\n"
            elif any_count == 1 and combo[0] == combo[1] and combo[0] != SlotEmoji.ANY:
                # Two of the same symbol
                emoji = non_any[0]
                message += f"Any two {emoji}: x{entry.payout_mult} (${payout_amount})\n"
            else:
                # Any other combo
                message += f"Any combo of {''.join(non_any)}: x{entry.payout_mult} (${payout_amount})\n"

        message += f"\nBet Amount = ${bet_cents/100:.2f}"
        return message


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
        self.dev_mode = self.config["bot"]["dev_mode"]

        game_settings = self.config.get("game_settings", {})
        slot_machine_settings = game_settings.get("slot_machine", {})

        paytable_config = slot_machine_settings.get("paytable", [])
        self.paytable = Paytable(paytable_config)

        self.bet_cents = slot_machine_settings.get("bet_cents", 25)


config = Config(config_filename)


# gambler info handler class
class GamblerInfoHandler:
    def __init__(self, db_filename: str) -> None:
        self.db_filename = db_filename
        self.connection = sqlite3.connect(self.db_filename, check_same_thread=False)

        cursor = self.connection.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Gambler_Tally (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            tally TEXT NOT NULL,
            balance_cents INTEGER NOT NULL,
            username TEXT
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Gambler_Ledger (
            trans_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            value INTEGER NOT NULL,
            slot_paytable TEXT,
            bet_cents INTEGER
        );
        """)

        # v1 db adds username
        cursor.execute("PRAGMA user_version;")
        db_ver = cursor.fetchone()
        if db_ver[0] < 1:
            cursor.execute("ALTER TABLE Gambler_Tally ADD COLUMN username TEXT;")
            cursor.execute("PRAGMA user_version = 1")

        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA synchronous = NORMAL;")
        cursor.execute("PRAGMA cache_size = 1000;")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_gambler_id ON Gambler_Tally(id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_user_id ON Gambler_Ledger(user_id);")

        self.connection.commit()

        self.setup_slot_machine_values()

    def __del__(self):
        if hasattr(self, 'connection'):
            self.connection.close()

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

    def init_data(self, id: int, name: str, username: str) -> dict[int, str, list, int]:
        # telegram's slot machine is a 1-64 RNG, each number corresponds to a 3 slot combo
        tally = []
        for x in range(64):
            tally.append(0)
        tally_json = json.dumps(tally)

        # store money as cents, makes more cents than real ahahahaaaa
        balance_cents = 0

        cursor = self.connection.cursor()
        query = """
        INSERT INTO Gambler_Tally (id, name, tally, balance_cents, username)
        VALUES (?, ?, ?, ?, ?);
        """
        entry_data = (id, name, tally_json, balance_cents, username)
        cursor.execute(query, entry_data)
        self.connection.commit()

        return {
            "id": id,
            "name": name,
            "tally": json.loads(tally_json),
            "balance_cents": balance_cents,
            "username": username,
        }

    def get_data(self, id: int, name: str, username: str) -> dict[int, str, list, int]:
        cursor = self.connection.cursor()
        query = """
            SELECT id, name, tally, balance_cents, username FROM Gambler_Tally WHERE id=?;
        """
        cursor.execute(query, (id,))
        data = cursor.fetchone()

        if data is None:
            return self.init_data(id, name, username)
        else:
            return {
                "id": data[0],
                "name": data[1],
                "tally": json.loads(data[2]),
                "balance_cents": data[3],
                "username": data[4],
            }

    def get_leaderboard(self, limit: int) -> list[dict[int, str, list, int]]:
        cursor = self.connection.cursor()
        query = """
            SELECT id, name, tally, balance_cents FROM Gambler_Tally ORDER BY balance_cents DESC LIMIT ?;
        """
        cursor.execute(query, (limit,))
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
        cursor = self.connection.cursor()

        query = """
            SELECT balance_cents FROM Gambler_Tally WHERE id = ?;
        """
        cursor.execute(query, (id,))
        balance_result = cursor.fetchone()

        if balance_result is None:
            return 0  # User not found

        balance = balance_result[0]

        query = """
            SELECT COUNT(*) FROM Gambler_Tally WHERE balance_cents > ?;
        """
        cursor.execute(query, (balance,))
        rank_above = cursor.fetchone()[0]

        return rank_above + 1

    def update_user_data(self, id: int, name: str, username: str) -> None:
        cursor = self.connection.cursor()
        query = """
            UPDATE Gambler_Tally SET name = ?, username = ? WHERE id = ?;
        """
        entry_data = (name, username, id)
        cursor.execute(query, entry_data)
        self.connection.commit()

    def process_slot_machine(self, id: int, name: str, username: str, value: int, 
                             emoji: str, slot_payout_table: list, bet_cents: int) -> int:
        """Process a slot machine play and update all relevant info"""
        if config.dev_mode:
            return 0

        data = self.get_data(id, name, username)

        tally = data["tally"]
        tally[value - 1] += 1
        tally_json = json.dumps(tally)
        
        balance = data["balance_cents"]
        balance -= bet_cents  # Cost of play

        payout_mult = config.paytable.get_payout_multiplier(value, gambler_info_handler.SLOT_MACHINE_VALUE)

        balance_add = payout_mult * bet_cents
        balance += balance_add

        cursor = self.connection.cursor()
        try:
            cursor.execute("BEGIN TRANSACTION")

            # Update tally & balance
            query = """
                UPDATE Gambler_Tally 
                SET tally = ?, balance_cents = ? 
                WHERE id = ?;
            """
            cursor.execute(query, (tally_json, balance, id))

            # Record transaction
            query = """
                INSERT INTO Gambler_Ledger (user_id, emoji, value, slot_paytable, bet_cents)
                VALUES (?, ?, ?, ?, ?);
            """

            paytable_json = json.dumps([entry.to_dict() for entry in config.paytable.entries])
            entry_data = (id, emoji, value, paytable_json, bet_cents)
            cursor.execute(query, entry_data)

            cursor.execute("COMMIT")
            return balance

        except Exception as e:
            cursor.execute("ROLLBACK")
            logger.error(f"Transaction failed: {e}")
            return data["balance_cents"]  # Return original balance on fail


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

    # update name and username
    gambler_info_handler.update_user_data(id, name, username)

    if reply_to_message_obj is not None:
        reply_to_user_id = reply_to_message_obj.from_user.id
        reply_to_user_name = reply_to_message_obj.from_user.full_name
        reply_to_user_username = reply_to_message_obj.from_user.username
        username = reply_to_message_obj.from_user.username
        data = gambler_info_handler.get_data(
            reply_to_user_id, reply_to_user_name, reply_to_user_username
        )
    else:
        data = gambler_info_handler.get_data(id, name, username)

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
{SlotEmoji.SEVEN.value*3}: {data["tally"][triple_seven]}
{SlotEmoji.BAR.value*3}: {data["tally"][triple_bar]}
{SlotEmoji.LEMON.value*3}: {data["tally"][triple_lemon]}
{SlotEmoji.GRAPE.value*3}: {data["tally"][triple_grape]}

Balance: {"" if data["balance_cents"]>=0 else "-"}${abs(data["balance_cents"])/100:.2f}
"""
    await update.message.reply_text(message)


@command_handler("paytable")
async def paytable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = config.paytable.to_display_string(config.bet_cents)
    await update.message.reply_text(message)


@command_handler("leaderboard")
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user_id = update.message.from_user.id
    current_user_name = update.message.from_user.full_name
    current_user_username = update.message.from_user.username

    top_users = gambler_info_handler.get_leaderboard(10)

    top_users = [user for user in top_users if sum(user["tally"]) > 0]

    if not top_users:
        await update.message.reply_text(
            "No gambling has taken place yet... Be the first to win big! 🎰"
        )
        return

    current_user_in_top = any(user["id"] == current_user_id for user in top_users)

    current_user_data = gambler_info_handler.get_data(
        current_user_id, current_user_name, current_user_username
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
    username = update.message.from_user.username
    value = update.message.dice.value
    data = gambler_info_handler.get_data(id, name, username)
    bet_cents = config.bet_cents

    balance = gambler_info_handler.process_slot_machine(
        id, name, username, value, Dice.SLOT_MACHINE, config.paytable, bet_cents
    )

    combo_name = gambler_info_handler.get_combo_name(value)

    data = gambler_info_handler.get_data(id, name, username)
    tally = data["tally"]

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
