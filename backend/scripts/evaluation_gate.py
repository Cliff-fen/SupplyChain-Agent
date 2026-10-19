"""Deterministic CI gate for routing, SQL safety and evidence metrics."""

from app.agents.graph import _heuristic_route
from app.core.sql_guard import SQLGuardError, validate_read_only_sql
from app.evals.service import answer_relevance, lexical_grounding, set_precision_recall


def main() -> None:
    routes = [
        ("统计各工厂库存趋势", "data"),
        ("库存周转率的定义和口径是什么", "knowledge"),
        ("结合制度口径统计各工厂订单趋势", "hybrid"),
    ]
    router_accuracy = sum(_heuristic_route(q)[0] == expected for q, expected in routes) / len(
        routes
    )
    sql_cases = [
        ("SELECT factory, SUM(qty) FROM inventory GROUP BY factory", True),
        ("DELETE FROM inventory", False),
        ("SELECT * FROM users", False),
    ]
    sql_correct = 0
    for sql, expected in sql_cases:
        try:
            validate_read_only_sql(sql, {"inventory"}, 500)
            accepted = True
        except SQLGuardError:
            accepted = False
        sql_correct += accepted == expected
    sql_accuracy = sql_correct / len(sql_cases)
    precision, recall = set_precision_recall(["c1", "c2"], ["c1", "c2"])
    faithfulness = lexical_grounding(
        "库存周转率等于销售成本除以平均库存",
        ["库存周转率等于销售成本除以平均库存"],
    )
    relevance = answer_relevance("库存周转率如何计算", "库存周转率计算使用销售成本和平均库存")
    metrics = {
        "router_accuracy": router_accuracy,
        "sql_guard_accuracy": sql_accuracy,
        "citation_precision": precision,
        "citation_recall": recall,
        "faithfulness": faithfulness,
        "answer_relevance": relevance,
    }
    thresholds = {
        "router_accuracy": 0.8,
        "sql_guard_accuracy": 1.0,
        "citation_precision": 0.8,
        "citation_recall": 0.8,
        "faithfulness": 0.75,
        "answer_relevance": 0.6,
    }
    failed = [name for name, threshold in thresholds.items() if metrics[name] < threshold]
    print({name: round(value, 4) for name, value in metrics.items()})
    if failed:
        raise SystemExit("Evaluation gates failed: " + ", ".join(failed))


if __name__ == "__main__":
    main()
