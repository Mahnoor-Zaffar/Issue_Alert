#!/usr/bin/env python3
"""Reset all issue data for a fresh test run."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.store import clear_all_data, init_db

if __name__ == "__main__":
    init_db()
    clear_all_data()
    print("Database cleared — next poll will treat all GitHub results as new.")
