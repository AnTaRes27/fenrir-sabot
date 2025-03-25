"""
User models
"""

from typing import List, TypedDict

class GamblerData(TypedDict):
    id: int
    name: str
    tally: List[int]
    balance_cents: int
    username: str

class LeaderboardEntry(TypedDict):
    id: int
    name: str
    tally: List[int]
    balance_cents: int
