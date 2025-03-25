#!/usr/bin/env python

"""
Database handler
"""

import json
import logging
import sqlite3
from typing import List

from ..models.user import GamblerData, LeaderboardEntry
from ..models.paytable import Paytable, SlotEmoji
from ..config import Config

logger = logging.getLogger(__name__)


class DbHandler:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.db_filename = config.db_filename
        self.connection = sqlite3.connect(self.db_filename, check_same_thread=False)

        cursor = self.connection.cursor()
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS Gambler_Tally (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            tally TEXT NOT NULL,
            balance_cents INTEGER NOT NULL,
            username TEXT
        );
        """
        )
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS Gambler_Ledger (
            trans_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            value INTEGER NOT NULL,
            slot_paytable TEXT,
            bet_cents INTEGER
        );
        """
        )

        # v1 db adds username
        cursor.execute("PRAGMA user_version;")
        db_ver = cursor.fetchone()
        if db_ver[0] < 1:
            cursor.execute("ALTER TABLE Gambler_Tally ADD COLUMN username TEXT;")
            cursor.execute("PRAGMA user_version = 1")

        # Performance optimizations
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA synchronous = NORMAL;")
        cursor.execute("PRAGMA cache_size = 1000;")

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_gambler_id ON Gambler_Tally(id);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_ledger_user_id ON Gambler_Ledger(user_id);"
        )

        self.connection.commit()

        self.setup_slot_machine_values()

    def __del__(self):
        if hasattr(self, "connection"):
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

    def init_data(self, id: int, name: str, username: str) -> GamblerData:
        # Telegram's slot machine is a 1-64 RNG, each number corresponds to a 3 slot combo
        tally_json = json.dumps([0] * 64)

        # store money as cents, makes more cents than real ahahahaaaa
        balance_cents = 0

        cursor = self.connection.cursor()
        query = """
        INSERT INTO Gambler_Tally (id, name, tally, balance_cents, username)
        VALUES (?, ?, ?, ?, ?);
        """
        cursor.execute(query, (id, name, tally_json, balance_cents, username))
        self.connection.commit()

        return {
            "id": id,
            "name": name,
            "tally": json.loads(tally_json),
            "balance_cents": balance_cents,
            "username": username,
        }

    def get_data(self, id: int, name: str, username: str) -> GamblerData:
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

    def get_leaderboard(self, limit: int) -> List[LeaderboardEntry]:
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

    def process_slot_machine(
        self,
        id: int,
        name: str,
        username: str,
        value: int,
        emoji: str,
        paytable: Paytable,
        bet_cents: int,
    ) -> int:
        """Processes a slot machine play and updates all relevant info, returning the new balance"""

        if self.config.dev_mode:
            return 0

        data = self.get_data(id, name, username)

        # Calculate new values
        tally = data["tally"]
        tally[value - 1] += 1
        tally_json = json.dumps(tally)

        balance = data["balance_cents"]
        balance -= bet_cents  # Cost of play

        # Get payout multiplier from paytable
        slot_result = self.SLOT_MACHINE_VALUE[value]

        # Convert tuple of symbol names to emoji values for matching
        slot_emojis = tuple(SlotEmoji[symbol.upper()].value for symbol in slot_result)

        # Find payout multiplier
        payout_mult = 0
        for entry in paytable.entries:
            if entry.matches(slot_emojis):
                payout_mult = entry.payout_mult
                break

        # Calculate winnings
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
            cursor.execute(query, (id, emoji, value, paytable.serialized, bet_cents))

            self.connection.commit()
            return balance

        except Exception as e:
            cursor.execute("ROLLBACK")
            logger.error(f"Transaction failed: {e}")
            return data["balance_cents"]  # Return original balance on fail
