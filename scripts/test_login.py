"""Step 1: can we log in to Angel One without typing anything?"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import broker  # noqa: E402

client = broker.login()
print("Login OK")
broker.logout(client)