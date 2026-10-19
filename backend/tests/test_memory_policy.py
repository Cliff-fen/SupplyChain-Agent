import pytest

from app.memory.service import MemoryPolicyError, MemoryService


def test_memory_policy_allows_preferences_and_rejects_secrets() -> None:
    MemoryService.validate("kpi_interest", "我关注库存周转率", 0.95)
    with pytest.raises(MemoryPolicyError, match="Sensitive"):
        MemoryService.validate("communication", "api_key=sk-private", 0.99)
    with pytest.raises(MemoryPolicyError, match="category"):
        MemoryService.validate("raw_business_data", "订单明细", 0.99)
    with pytest.raises(MemoryPolicyError, match="confidence"):
        MemoryService.validate("communication", "简洁回答", float("nan"))
