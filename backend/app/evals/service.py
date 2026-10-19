import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import _heuristic_route
from app.core.config import get_settings
from app.core.sql_guard import SQLGuardError, validate_read_only_sql
from app.models import DatasetVersion, EvaluationRun, ModelVersion, TrainingExample
from app.services.llm import OpenAICompatibleClient


def _terms(text: str) -> set[str]:
    return {item.lower() for item in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text)}


def set_precision_recall(actual: list[str], expected: list[str]) -> tuple[float, float]:
    actual_set, expected_set = set(actual), set(expected)
    overlap = len(actual_set & expected_set)
    precision = overlap / len(actual_set) if actual_set else float(not expected_set)
    recall = overlap / len(expected_set) if expected_set else 1.0
    return precision, recall


def lexical_grounding(answer: str, contexts: list[str]) -> float:
    answer_terms = _terms(answer)
    if not answer_terms:
        return 0.0
    context_terms = _terms(" ".join(contexts))
    return len(answer_terms & context_terms) / len(answer_terms)


def answer_relevance(question: str, answer: str) -> float:
    question_terms = _terms(question)
    if not question_terms:
        return 0.0
    return len(question_terms & _terms(answer)) / len(question_terms)


async def run_evaluation(session: AsyncSession, evaluation: EvaluationRun) -> None:
    version = await session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.id == evaluation.dataset_version_id,
            DatasetVersion.tenant_id == evaluation.tenant_id,
        )
    )
    if not version:
        raise ValueError("Evaluation dataset version not found")
    examples = list(
        await session.scalars(
            select(TrainingExample).where(
                TrainingExample.dataset_id == version.dataset_id,
                TrainingExample.tenant_id == evaluation.tenant_id,
                TrainingExample.status == "approved",
            )
        )
    )
    if not examples:
        raise ValueError("Evaluation dataset has no approved examples")

    evaluation.status = "running"
    await session.commit()
    scores: dict[str, list[float]] = {
        "router_accuracy": [],
        "sql_guard_accuracy": [],
        "citation_precision": [],
        "citation_recall": [],
        "faithfulness": [],
        "answer_relevance": [],
    }
    client = OpenAICompatibleClient()
    for example in examples:
        source, target = example.input_payload, example.target_payload
        if example.kind == "intent":
            predicted = source.get("predicted_route")
            if not predicted:
                try:
                    predicted, _ = await client.route_question(str(source.get("question", "")))
                except RuntimeError:
                    predicted, _ = _heuristic_route(str(source.get("question", "")))
            scores["router_accuracy"].append(float(predicted == target.get("route")))
        elif example.kind == "sql":
            try:
                validate_read_only_sql(
                    str(source.get("sql", "")),
                    set(source.get("allowed_tables", [])),
                    500,
                )
                accepted = True
            except SQLGuardError:
                accepted = False
            scores["sql_guard_accuracy"].append(float(accepted == target.get("accepted")))
        elif example.kind == "answer":
            answer = str(source.get("answer", ""))
            question = str(source.get("question", ""))
            contexts = [str(item) for item in source.get("contexts", [])]
            precision, recall = set_precision_recall(
                source.get("citation_ids", []), target.get("citation_ids", [])
            )
            scores["citation_precision"].append(precision)
            scores["citation_recall"].append(recall)
            scores["faithfulness"].append(lexical_grounding(answer, contexts))
            scores["answer_relevance"].append(answer_relevance(question, answer))

    metrics = {
        name: round(sum(values) / len(values), 4) if values else None
        for name, values in scores.items()
    }
    settings = get_settings()
    thresholds = {
        "router_accuracy": settings.eval_router_accuracy_min,
        "sql_guard_accuracy": settings.eval_sql_guard_accuracy_min,
        "citation_precision": settings.eval_citation_precision_min,
        "citation_recall": settings.eval_citation_recall_min,
        "faithfulness": settings.eval_faithfulness_min,
        "answer_relevance": settings.eval_answer_relevance_min,
    }
    failed = [
        name
        for name, threshold in thresholds.items()
        if metrics[name] is not None and metrics[name] < threshold
    ]
    evaluation.metrics = {
        **metrics,
        "thresholds": thresholds,
        "failed_gates": failed,
        "example_count": len(examples),
    }
    evaluation.status = "failed_gate" if failed else "completed"
    evaluation.failure_reason = ", ".join(failed) or None
    if evaluation.model_version_id:
        model = await session.scalar(
            select(ModelVersion).where(
                ModelVersion.id == evaluation.model_version_id,
                ModelVersion.tenant_id == evaluation.tenant_id,
            )
        )
        if model:
            model.evaluation_report = evaluation.metrics
            model.status = "rejected" if failed else "validated"
    await session.commit()
