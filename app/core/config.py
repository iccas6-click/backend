from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")

MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "click_backend_db")
MYSQL_USER = os.environ.get("MYSQL_USER", "click_user")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "click0623")
