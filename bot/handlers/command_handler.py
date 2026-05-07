from bot.services import supabase_service, telegram_service
from bot.utils.formatters import format_welcome, format_help


def handle_start(chat_id: int, user_name: str | None = None) -> None:
    supabase_service.clear_session(chat_id)
    telegram_service.send_message(chat_id, format_welcome(user_name))


def handle_help(chat_id: int) -> None:
    telegram_service.send_message(chat_id, format_help())
