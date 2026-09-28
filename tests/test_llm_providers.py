from pathlib import Path
import sys
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.llm_providers import CompatibleChatProvider  # noqa: E402


def test_openai_compatible_provider_uses_configured_endpoint_and_bearer(monkeypatch):
    response = Mock(ok=True)
    response.json.return_value = {"choices": [{"message": {"content": "structured answer"}}]}
    request = Mock(return_value=response)
    monkeypatch.setattr("app.llm_providers.requests.post", request)
    provider = CompatibleChatProvider("groq", "secret", "test-model", "https://api.example/v1")

    content, error = provider.complete("system", "user", 0.0, 100)

    assert content == "structured answer"
    assert error is None
    request.assert_called_once()
    assert request.call_args.args[0] == "https://api.example/v1/chat/completions"
    assert request.call_args.kwargs["headers"]["Authorization"] == "Bearer secret"


def test_sarvam_provider_uses_its_endpoint_and_subscription_key(monkeypatch):
    response = Mock(ok=True)
    response.json.return_value = {"choices": [{"message": {"content": "answer"}}]}
    request = Mock(return_value=response)
    monkeypatch.setattr("app.llm_providers.requests.post", request)
    provider = CompatibleChatProvider("sarvam", "secret", "sarvam-model", "https://api.sarvam.ai")

    content, error = provider.complete("system", "user", 0.0, 100)

    assert content == "answer"
    assert error is None
    assert request.call_args.args[0] == "https://api.sarvam.ai/v1/chat/completions"
    assert request.call_args.kwargs["headers"]["api-subscription-key"] == "secret"


def test_provider_without_key_fails_without_network_call(monkeypatch):
    request = Mock()
    monkeypatch.setattr("app.llm_providers.requests.post", request)
    provider = CompatibleChatProvider("openai", None, "test-model", "https://api.example/v1")

    content, error = provider.complete("system", "user", 0.0, 100)

    assert content is None
    assert error == "no api key configured"
    request.assert_not_called()