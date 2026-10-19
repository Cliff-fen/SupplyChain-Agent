import pytest

from app.services.llm import ModelConfigurationError, OpenAICompatibleClient


@pytest.mark.asyncio
async def test_analysis_requires_real_model_configuration(monkeypatch) -> None:
    monkeypatch.delenv("SUPPLYMIND_CHAT_BASE_URL", raising=False)
    monkeypatch.delenv("SUPPLYMIND_CHAT_MODEL", raising=False)
    monkeypatch.delenv("SUPPLYMIND_CHAT_API_KEY", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(ModelConfigurationError):
        await OpenAICompatibleClient().plan_sql("show shortage risk", ["inventory_risk"])


@pytest.mark.asyncio
async def test_embedding_requires_real_model_configuration(monkeypatch) -> None:
    monkeypatch.delenv("SUPPLYMIND_EMBEDDING_BASE_URL", raising=False)
    monkeypatch.delenv("SUPPLYMIND_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("SUPPLYMIND_EMBEDDING_API_KEY", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(ModelConfigurationError):
        await OpenAICompatibleClient().embed(["production rate"])
