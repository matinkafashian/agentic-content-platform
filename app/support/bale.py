from app.support.telegram import TelegramSupportBot


class BaleSupportBot(TelegramSupportBot):
    """Receive private Bale messages through its Telegram-compatible Bot API."""

    platform = "bale"
    api_base_url = "https://tapi.bale.ai"
