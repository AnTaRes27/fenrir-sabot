#!/usr/bin/env python

"""
Slot machine paytable and emoji models
"""

from enum import Enum
import json
import logging
from typing import List, Dict, Tuple, Any

logger = logging.getLogger(__name__)

class SlotEmoji(str, Enum):
    """Enum for slot machine emoji with readable names"""
    SEVEN = "7️⃣"
    BAR = "◼️"
    LEMON = "🍋"
    GRAPE = "🍇"
    ANY = ""

    @classmethod
    def from_value(cls, value: str) -> 'SlotEmoji':
        """Convert emoji string to enum value"""
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
        """Check if a slot result matches this paytable entry"""
        if len(self.combo) != len(slot_result):
            return False
            
        for i, emoji in enumerate(self.combo):
            if emoji != SlotEmoji.ANY and emoji.value != slot_result[i]:
                return False
        return True
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "combo": [emoji.value for emoji in self.combo],
            "payout_mult": self.payout_mult
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PaytableEntry':
        """Create from dictionary (deserialization)"""
        return cls(data["combo"], data["payout_mult"])
        
    def __str__(self) -> str:
        """String representation for display"""
        emoji_str = ''.join([emoji.value if emoji != SlotEmoji.ANY else '*' for emoji in self.combo])
        return f"{emoji_str}: x{self.payout_mult}"

class Paytable:
    """Handles paytable operations and lookups"""
    def __init__(self, paytable_config):
        self.entries: List[PaytableEntry] = []
        self._load_from_config(paytable_config)

    def _load_from_config(self, paytable_config) -> None:
        """Load paytable from config data"""
        if isinstance(paytable_config, list):
            if len(paytable_config) == 0:
                raise ValueError("Empty paytable config")
            paytable_data = paytable_config
        else:
            paytable_data = json.loads(paytable_config)

        self.serialized = json.dumps(paytable_data)
        self.entries = [PaytableEntry.from_dict(entry) for entry in paytable_data]

    def _setup_default_paytable(self) -> None:
        """Create a default paytable in case of config errors"""
        self.entries = [
            PaytableEntry([SlotEmoji.SEVEN.value, SlotEmoji.SEVEN.value, SlotEmoji.SEVEN.value], 80),
            PaytableEntry([SlotEmoji.BAR.value, SlotEmoji.BAR.value, SlotEmoji.BAR.value], 40),
            PaytableEntry([SlotEmoji.LEMON.value, SlotEmoji.LEMON.value, SlotEmoji.LEMON.value], 10),
            PaytableEntry([SlotEmoji.GRAPE.value, SlotEmoji.GRAPE.value, SlotEmoji.GRAPE.value], 10),
            PaytableEntry([SlotEmoji.BAR.value, SlotEmoji.BAR.value, SlotEmoji.ANY.value], 1),
        ]

    def get_payout_multiplier(self, value: int, slot_mappings: Dict[int, Tuple[str, str, str]]) -> int:
        """Get the payout multiplier for a specific slot value"""
        if value not in slot_mappings:
            return 0
            
        slot_result = slot_mappings[value]
        
        # Convert tuple of symbol names to tuple of emoji for matching
        slot_emojis = tuple(SlotEmoji[symbol.upper()].value for symbol in slot_result)
        
        # Find matching paytable entry
        for entry in self.entries:
            if entry.matches(slot_emojis):
                return entry.payout_mult
                
        return 0  # No match found
        
    def to_display_string(self, bet_cents: int) -> str:
        """Generate a readable paytable display for users"""
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
                message += f"{emoji.value*3}: x{entry.payout_mult} (${payout_amount})\n"
            elif any_count == 2 and len(non_any) == 1:
                # One specific symbol anywhere
                emoji = non_any[0]
                message += f"Any {emoji.value}: x{entry.payout_mult} (${payout_amount})\n"
            elif any_count == 1 and combo[0] == combo[1] and combo[0] != SlotEmoji.ANY:
                # Two of the same symbol
                emoji = non_any[0]
                message += f"Any two {emoji.value}: x{entry.payout_mult} (${payout_amount})\n"
            else:
                # Any other combination
                message += f"Any combo of {''.join([e.value for e in non_any])}: x{entry.payout_mult} (${payout_amount})\n"
                
        message += f"\nBet Amount = ${bet_cents/100:.2f}"
        return message
