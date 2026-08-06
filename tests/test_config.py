import boto3
import pytest
from moto import mock_aws

from config import Config, load_config

ENV_NAMES = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GEMINI_API_KEY"]


def test_env_vars_take_precedence(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("GEMINI_API_KEY", "gem")
    assert load_config() == Config("tok", "123", "gem")


def test_falls_back_to_ssm(aws_env, monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    with mock_aws():
        ssm = boto3.client("ssm")
        for name, value in [
            ("/infra-feed/telegram-bot-token", "tok"),
            ("/infra-feed/telegram-chat-id", "123"),
            ("/infra-feed/gemini-api-key", "gem"),
        ]:
            ssm.put_parameter(Name=name, Value=value, Type="SecureString")
        assert load_config() == Config("tok", "123", "gem")
