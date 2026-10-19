from app.services.retrieval import cosine_similarity


def test_cosine_similarity_is_rankable() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine_similarity([1.0], [1.0, 0.0]) == 0.0
