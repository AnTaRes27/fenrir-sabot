#!/usr/bin/env python

"""
Configuration handler
"""

import os
import sys
import logging
import shutil
import yaml

from .models.paytable import Paytable

logger = logging.getLogger(__name__)

class Config:
    def __init__(self, config_filename: str) -> None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
        # Config file should be in the project root -> src
        config_path = os.path.join(project_root, "src", config_filename)
        default_config_path = os.path.join(project_root, "default_config.yaml")
        
        self.config_filename = config_filename

        try:
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"No config file found at {config_path}, creating one...")
            try:
                shutil.copyfile(default_config_path, config_path)
                logger.warning(
                    f"Insert API key in {config_path} and rerun"
                )
            except FileNotFoundError:
                logger.error(f"Default config file not found at {default_config_path}")
            sys.exit(1)

        self.db_filename = self.config["database"]["filename"]
        self.token = self.config["bot"]["token"]
        self.dev_mode = self.config["bot"]["dev_mode"]

        game_settings = self.config.get("game_settings", {})
        slot_machine_settings = game_settings.get("slot_machine", {})

        paytable_config = slot_machine_settings.get("paytable", [])
        self.paytable = Paytable(paytable_config)

        self.bet_cents = slot_machine_settings.get("bet_cents", 25)
