import os
from dataclasses import dataclass

import boto3

PARAM_PREFIX = "/infra-feed"


@dataclass
class Config:
    telegram_bot_token: str
    telegram_chat_id: str
    gemini_api_key: str


def load_config() -> Config:
    return Config(
        telegram_bot_token=_get("TELEGRAM_BOT_TOKEN", "telegram-bot-token"),
        telegram_chat_id=_get("TELEGRAM_CHAT_ID", "telegram-chat-id"),
        gemini_api_key=_get("GEMINI_API_KEY", "gemini-api-key"),
    )


def _get(env_name: str, param_name: str) -> str:
    value = os.environ.get(env_name)
    if value:
        return value
    ssm = boto3.client("ssm")
    response = ssm.get_parameter(
        Name=f"{PARAM_PREFIX}/{param_name}", WithDecryption=True
    )
    return response["Parameter"]["Value"]
