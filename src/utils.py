#!/usr/bin/env python

"""
Utility funcs
"""

def parse_dollar_amount(amount: int) -> str:
    """Convert cents to displayable dollar amount"""
    signum = "-" if amount < 0 else ""
    return f"{signum}${abs(amount)/100:.2f}"
