from app.rag.ranking import bm25_score, reciprocal_rank_fusion, term_frequencies, tokenize


def test_multilingual_tokenizer_and_term_frequencies() -> None:
    tokens = tokenize("生产达成率 production_rate")
    assert "生产" in tokens
    assert "production_rate" in tokens
    frequencies, length = term_frequencies("库存 库存 inventory")
    assert frequencies["库"] == 2
    assert length >= 3


def test_bm25_rewards_relevance_and_rrf_is_deterministic() -> None:
    relevant = bm25_score(3, 2, 100, 120, 1000)
    weak = bm25_score(1, 2, 300, 120, 1000)
    assert relevant > weak > 0
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]], k=60)
    assert fused[0][0] == "b"
    assert dict(fused)["a"] == 1 / 61
    assert dict(fused)["c"] == 1 / 62
