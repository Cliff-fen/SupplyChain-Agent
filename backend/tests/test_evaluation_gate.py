from app.evals.service import answer_relevance, lexical_grounding, set_precision_recall


def test_evidence_metrics_reward_grounded_cited_answer() -> None:
    precision, recall = set_precision_recall(["c1", "c2"], ["c1", "c2"])
    assert precision == recall == 1.0
    assert lexical_grounding("库存周转率等于销售成本除以平均库存", ["库存周转率等于销售成本除以平均库存"]) == 1.0
    assert answer_relevance("库存周转率如何计算", "库存周转率计算使用销售成本和平均库存") >= 0.6


def test_evidence_metrics_penalize_unrelated_or_missing_citations() -> None:
    precision, recall = set_precision_recall(["wrong"], ["c1"])
    assert precision == recall == 0.0
    assert lexical_grounding("完全无关的内容", ["库存周转率定义"]) < 0.5
