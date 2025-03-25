#!/usr/bin/env python

"""
Fenrir Sabot
"""

from __future__ import annotations

import argparse
import logging

from telegram import Update
from telegram.ext import ApplicationBuilder

from .config import Config
from .db.db_handler import DbHandler
from .handlers import commands, messages

logging.basicConfig(
    format="%(asctime)s - %(name)s - [%(levelname)s] %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Process arguments
argparser = argparse.ArgumentParser(description="FENRIR")
argparser.add_argument(
    "--config", default="config.yaml", type=str, help="Config filename"
)
args = argparser.parse_args()
config_filename = args.config

# Init config
config = Config(config_filename)

# Init db handler
db_handler = DbHandler(config)

# Init telegram bot
app = ApplicationBuilder().token(config.token).build()


def main() -> None:
    commands.init(app, config, db_handler)
    messages.init(app, config, db_handler)

    logger.info("Starting bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
