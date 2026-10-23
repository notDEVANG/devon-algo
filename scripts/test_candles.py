"""Step 2: pull ~1 year of daily candles for one stock and save them."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import broker  # noqa: E402
import config  # noqa: E402

client = broker.login()
token, trading_symbol = broker.find_token(config.TEST_SYMBOL)
print(f"{trading_symbol} -> token {token}")

df = broker.get_daily_candles(client, token, days=365)
print(f"Got {len(df)} daily candles")
print(df.tail())

out = config.DATA_DIR / f"{config.TEST_SYMBOL}_daily.csv"
df.to_csv(out, index=False)
print(f"Saved to {out}")
print("Compare the last close above with your broker app. They should match.")

broker.logout(client)