"""Telegram alerts."""
import requests

import config


def send(text: str) -> bool:
    config.require("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
        timeout=15,
    )
    if not resp.ok:
        print(f"Telegram error {resp.status_code}: {resp.text}")
    return resp.ok