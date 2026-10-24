"""Graph features on a ring fixture: A, B, C share device D; A is known fraud;
E is alone on device F."""
# pyrefly: ignore[missing-import]
from aegis_ml.features.graph_features import build_graph, compute

EDGES = [("account", "A", "device", "D", 1), ("account", "B", "device", "D", 3),
         ("account", "C", "device", "D", 1), ("account", "E", "device", "F", 1),
         ("account", "B", "device", "D", 1)]


def test_ring_fixture():
    f = compute(build_graph(EDGES), ["A"]).set_index("entity_id")
    assert f.loc[["A", "B", "C"], "component_size"].tolist() == [4, 4, 4]
    assert f.loc["E", "component_size"] == 2
    assert f.loc[["A", "B", "C", "E"], "dist_to_fraud"].tolist() == [0, 2, 2, -1]
    # E cannot be reached from A, so its rank is ~0 (PageRank converges iteratively)
    assert f.loc["E", "risk_rank"] < 1e-4 < f.loc["C", "risk_rank"] < f.loc["B", "risk_rank"]


def test_hop_count_ignores_edge_weight():
    heavy = [("account", "A", "device", "D", 1000), ("account", "B", "device", "D", 1000)]
    f = compute(build_graph(heavy), ["A"]).set_index("entity_id")
    assert f.loc["B", "dist_to_fraud"] == 2


def test_no_known_fraud_gives_defaults():
    f = compute(build_graph(EDGES), [])
    assert (f["dist_to_fraud"] == -1).all() and (f["risk_rank"] == 0.0).all()
