import math
import re
from collections import Counter


def tokenize(text: str) -> list[str]:
    lowered = text.lower()
    latin = re.findall(r"[a-z0-9_]+", lowered)
    chinese_groups = re.findall(r"[\u4e00-\u9fff]+", lowered)
    chinese: list[str] = []
    for group in chinese_groups:
        chinese.extend(group)
        chinese.extend(group[index : index + 2] for index in range(len(group) - 1))
    return [token[:160] for token in latin + chinese if token]


def term_frequencies(text: str) -> tuple[Counter[str], int]:
    tokens = tokenize(text)
    return Counter(tokens), len(tokens)


def bm25_score(
    term_frequency: int,
    document_frequency: int,
    document_length: int,
    average_document_length: float,
    document_count: int,
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    if not term_frequency or not document_frequency or not document_count:
        return 0.0
    average = average_document_length or 1.0
    inverse_document_frequency = math.log(
        1 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
    )
    denominator = term_frequency + k1 * (1 - b + b * document_length / average)
    return inverse_document_frequency * (term_frequency * (k1 + 1)) / denominator


def reciprocal_rank_fusion(rankings: list[list[str]], *, k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, identifier in enumerate(ranking, start=1):
            scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
