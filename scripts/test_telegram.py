"""Step 3: login + candles + Telegram message, end to end."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import broker  # noqa: E402
import config  # noqa: E402
import notify  # noqa: E402

client = broker.login()
token, trading_symbol = broker.find_token(config.TEST_SYMBOL)
df = broker.get_daily_candles(client, token, days=365)
last = df.iloc[-1]

ok = notify.send(
    f"Phase 0 OK: logged in, got {len(df)} candles for {trading_symbol}. "
    f"Last close {last['close']} on {last['timestamp'].date()}."
)
print("Telegram sent" if ok else "Telegram FAILED")

broker.logout(client)