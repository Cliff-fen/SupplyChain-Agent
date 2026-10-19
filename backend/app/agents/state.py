import operator
from typing import Annotated, Literal, TypedDict


def merge_maps(left: dict, right: dict) -> dict:
    return {**left, **right}


AgentRoute = Literal["data", "knowledge", "hybrid", "unsupported"]


class SupplyMindState(TypedDict, total=False):
    tenant_id: str
    user_id: str
    role: str
    run_id: str
    conversation_id: str
    question: str
    data_source_id: str
    knowledge_base_id: str
    route: AgentRoute
    route_confidence: float
    selected_subagents: list[str]
    messages: Annotated[list[dict], operator.add]
    memories: Annotated[list[dict], operator.add]
    subagent_results: Annotated[list[dict], operator.add]
    citations: Annotated[list[dict], operator.add]
    trace: Annotated[list[dict], operator.add]
    errors: Annotated[list[dict], operator.add]
    token_usage: Annotated[dict, merge_maps]
    attempts: Annotated[dict, merge_maps]
    answer: dict
    verified: bool
    verification_error: str | None
    retry_target: str | None
    requires_approval: bool
    approval: dict | None
    completed: bool
