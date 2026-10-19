import json
from collections.abc import AsyncIterator

import httpx
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.observability import model_operation


class ModelConfigurationError(RuntimeError):
    pass


class ModelResponseError(RuntimeError):
    pass


class AnswerPlan(BaseModel):
    direct_answer: str = Field(min_length=1)
    facts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class OpenAICompatibleClient:
    @staticmethod
    def _openai_messages(messages) -> list[dict[str, str]]:
        """Translate LangChain message types to OpenAI-compatible roles."""
        roles = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}
        return [
            {"role": roles.get(message.type, message.type), "content": message.content}
            for message in messages
        ]

    @model_operation("gen_ai.embedding")
    async def embed(self, texts: list[str]) -> list[list[float]]:
        settings = get_settings()
        if (
            not settings.embedding_base_url
            or not settings.embedding_model
            or not settings.embedding_api_key
        ):
            raise ModelConfigurationError(
                "Embedding model configuration is required for knowledge retrieval"
            )
        url = f"{settings.embedding_base_url.rstrip('/')}/embeddings"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
                json={"model": settings.embedding_model, "input": texts},
            )
        if response.status_code >= 400:
            raise ModelResponseError("Embedding model request failed")
        try:
            rows = response.json()["data"]
            vectors = [row["embedding"] for row in sorted(rows, key=lambda row: row["index"])]
            if len(vectors) != len(texts) or not all(
                isinstance(vector, list) for vector in vectors
            ):
                raise TypeError("Embedding response fields are invalid")
            return vectors
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModelResponseError("Embedding model returned an invalid response") from exc

    @model_operation("gen_ai.chat_json")
    async def _chat_json(
        self, prompt: str, *, model: str | None = None, temperature: float = 0
    ) -> dict:
        settings = get_settings()
        base_url = settings.llm_gateway_url or settings.chat_base_url
        if not base_url or not settings.chat_model or not settings.chat_api_key:
            raise ModelConfigurationError(
                "Chat model configuration is required before analysis can run"
            )
        async with httpx.AsyncClient(timeout=settings.chat_timeout_seconds) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.chat_api_key}"},
                json={
                    "model": model or settings.chat_model,
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": "Return valid JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
        if response.status_code >= 400:
            raise ModelResponseError("Chat model request failed")
        try:
            payload = json.loads(response.json()["choices"][0]["message"]["content"])
            if not isinstance(payload, dict):
                raise TypeError("JSON response must be an object")
            return payload
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ModelResponseError("Chat model returned invalid JSON") from exc

    async def optimize_retrieval_query(self, query: str, count: int = 3) -> dict:
        payload = await self._chat_json(
            "Optimize this enterprise supply-chain retrieval query. "
            f"Return keys queries (exactly {count} short alternative queries) and "
            "hypothetical_answer (a short HyDE passage; do not claim it is factual). "
            f"Query: {query}",
            model=get_settings().ai_router_model,
        )
        queries = payload.get("queries")
        hypothetical = payload.get("hypothetical_answer")
        if not isinstance(queries, list) or not all(isinstance(item, str) for item in queries):
            raise ModelResponseError("Query optimizer returned invalid queries")
        if hypothetical is not None and not isinstance(hypothetical, str):
            raise ModelResponseError("Query optimizer returned invalid HyDE text")
        return {"queries": queries[:count], "hypothetical_answer": hypothetical or ""}

    async def route_question(self, question: str) -> tuple[str, float]:
        payload = await self._chat_json(
            "Classify the request into data, knowledge, hybrid, or unsupported. "
            "Data needs database facts; knowledge needs policy/definition evidence; hybrid needs both. "
            f"Return route and confidence (0..1). Request: {question}",
            model=get_settings().ai_router_model,
        )
        route = payload.get("route")
        confidence = payload.get("confidence")
        if route not in {"data", "knowledge", "hybrid", "unsupported"}:
            raise ModelResponseError("Router returned an invalid route")
        if not isinstance(confidence, (int, float)):
            raise ModelResponseError("Router returned an invalid confidence")
        return route, min(1.0, max(0.0, float(confidence)))

    @model_operation("gen_ai.rerank")
    async def rerank(self, query: str, candidates: list[dict], limit: int) -> list[str]:
        settings = get_settings()
        if not candidates:
            return []
        if settings.rerank_base_url and settings.rerank_model and settings.rerank_api_key:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{settings.rerank_base_url.rstrip('/')}/rerank",
                    headers={"Authorization": f"Bearer {settings.rerank_api_key}"},
                    json={
                        "model": settings.rerank_model,
                        "query": query,
                        "documents": [item["text"] for item in candidates],
                        "top_n": limit,
                    },
                )
            if response.status_code >= 400:
                raise ModelResponseError("Rerank model request failed")
            try:
                indexes = [item["index"] for item in response.json()["results"]]
                return [candidates[index]["chunk_id"] for index in indexes[:limit]]
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise ModelResponseError("Rerank model returned invalid results") from exc
        payload = await self._chat_json(
            "Rank the evidence by relevance. Return ordered_chunk_ids only. "
            f"Query: {query}\nCandidates: "
            + json.dumps(
                [
                    {"chunk_id": item["chunk_id"], "text": item["text"][:1200]}
                    for item in candidates
                ],
                ensure_ascii=False,
            ),
            model=settings.ai_rerank_model or settings.ai_answer_model,
        )
        ordered = payload.get("ordered_chunk_ids")
        allowed = {item["chunk_id"] for item in candidates}
        if not isinstance(ordered, list):
            raise ModelResponseError("LLM reranker returned invalid results")
        return [item for item in ordered if isinstance(item, str) and item in allowed][:limit]

    async def extract_memories(self, question: str, answer: str) -> list[dict]:
        payload = await self._chat_json(
            "Extract only durable user preferences from this conversation. "
            "Allowed categories: communication, kpi_interest, factory_scope, product_line, "
            "time_range, role_context. Never extract credentials, personal identifiers, raw data, "
            "or temporary analysis facts. Return memories as objects with category, memory_key, "
            "content, confidence. Return an empty list when there is no durable preference. "
            f"User: {question}\nAssistant: {answer[:4000]}",
            model=get_settings().ai_router_model,
        )
        memories = payload.get("memories", [])
        if not isinstance(memories, list):
            raise ModelResponseError("Memory extractor returned invalid results")
        return [item for item in memories if isinstance(item, dict)]

    @model_operation("gen_ai.stream")
    async def stream_text(self, prompt: str, *, model: str | None = None) -> AsyncIterator[str]:
        settings = get_settings()
        base_url = settings.llm_gateway_url or settings.chat_base_url
        if not base_url or not settings.chat_model or not settings.chat_api_key:
            raise ModelConfigurationError(
                "Chat model configuration is required before analysis can run"
            )
        async with httpx.AsyncClient(timeout=settings.chat_stream_timeout_seconds) as client:
            async with client.stream(
                "POST",
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.chat_api_key}"},
                json={
                    "model": model or settings.ai_answer_model or settings.chat_model,
                    "temperature": 0,
                    "stream": True,
                    "messages": [{"role": "user", "content": prompt}],
                },
            ) as response:
                if response.status_code >= 400:
                    raise ModelResponseError("Streaming model request failed")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        token = json.loads(data)["choices"][0]["delta"].get("content")
                    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
                        continue
                    if token:
                        yield token

    @model_operation("gen_ai.sql_planner")
    async def plan_sql(
        self,
        question: str,
        schema: list[str] | list[dict],
        context: list[str] | None = None,
        previous_error: str | None = None,
    ) -> dict:
        settings = get_settings()
        if not settings.chat_base_url or not settings.chat_model or not settings.chat_api_key:
            raise ModelConfigurationError(
                "Chat model configuration is required before analysis can run"
            )
        schema_text = "; ".join(
            f"{item.get('name')}: "
            + ", ".join(column.get("name", "") for column in item.get("columns", []))
            if isinstance(item, dict)
            else str(item)
            for item in schema
        )
        context_text = "\n".join(context[-8:]) if context else "（无历史上下文）"
        prompt_template = ChatPromptTemplate.from_messages(
            [("system", "Return valid JSON only."), ("user", "{prompt}")]
        )
        prompt = (
            "You are a read-only manufacturing analytics SQL planner. Return only JSON with keys sql and insight. "
            "Use only the allowed tables. SQL must be a single SELECT or WITH statement. "
            "Use the current question as the source of truth. Use history only to resolve references such as '它' or '继续看', "
            "and never repeat an old question as a new task. "
            f"Allowed tables and columns: {schema_text}. Never invent column names. "
            + (
                f"The previous plan was rejected: {previous_error}. Correct that exact issue and return a new plan. "
                if previous_error
                else ""
            )
            + f"Recent conversation:\n{context_text}\nCurrent user question: {question}"
        )
        formatted_prompt = prompt_template.format_messages(prompt=prompt)
        url = f"{settings.chat_base_url.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=settings.planner_timeout_seconds) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.chat_api_key}"},
                json={
                    "model": settings.chat_model,
                    "temperature": 0,
                    "messages": self._openai_messages(formatted_prompt),
                },
            )
        if response.status_code >= 400:
            raise ModelResponseError("Chat model request failed")
        try:
            content = response.json()["choices"][0]["message"]["content"]
            result = json.loads(content)
            if not isinstance(result.get("sql"), str) or not isinstance(result.get("insight"), str):
                raise TypeError("Model plan fields are invalid")
            return {"sql": result["sql"], "insight": result["insight"]}
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ModelResponseError("Chat model returned an invalid analysis plan") from exc

    @model_operation("gen_ai.answer")
    async def answer_question(
        self,
        question: str,
        rows: list[dict],
        citations: list[dict],
        context: list[str] | None = None,
        planner_insight: str = "",
    ) -> AnswerPlan:
        """Generate an evidence-bound answer using LangChain structured output."""
        settings = get_settings()
        if not settings.chat_base_url or not settings.chat_model or not settings.chat_api_key:
            raise ModelConfigurationError(
                "Chat model configuration is required before analysis can run"
            )
        parser = PydanticOutputParser(pydantic_object=AnswerPlan)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an enterprise supply-chain analyst. Answer only from the supplied query rows and citations. {format_instructions}",
                ),
                (
                    "user",
                    "Question: {question}\nPlanner note: {planner_insight}\nRows: {rows}\nCitations: {citations}\nContext: {context}",
                ),
            ]
        )
        messages = prompt.format_messages(
            format_instructions=parser.get_format_instructions(),
            question=question,
            planner_insight=planner_insight,
            rows=json.dumps(rows[:100], ensure_ascii=False, default=str),
            citations=json.dumps(citations[:10], ensure_ascii=False, default=str),
            context="\n".join((context or [])[-8:]) or "（无历史上下文）",
        )
        url = f"{settings.chat_base_url.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=settings.planner_timeout_seconds) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.chat_api_key}"},
                json={
                    "model": settings.ai_answer_model or settings.chat_model,
                    "temperature": 0,
                    "messages": self._openai_messages(messages),
                },
            )
        if response.status_code >= 400:
            raise ModelResponseError("Chat model answer request failed")
        try:
            content = response.json()["choices"][0]["message"]["content"]
            return parser.parse(content)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ModelResponseError("Chat model returned an invalid structured answer") from exc
