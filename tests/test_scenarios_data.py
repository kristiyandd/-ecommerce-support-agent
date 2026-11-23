import json

from support_agent.harness import DEFAULT_SCENARIOS

ASSIGNMENT_REQUESTS = [
    ("scenario-01", "CUST-001", "Where is order ORD-100?"),
    ("scenario-02", "CUST-001", "One of the wine glasses in order ORD-200 arrived broken. Can I get a refund for it?"),
    ("scenario-03", "CUST-001", "What is the status of order ORD-204?"),
    (
        "scenario-04",
        "CUST-001",
        "Hi, I returned the Travel Mug from order ORD-300 last week and I can see that the return has already "
        "been received. I was expecting a refund of €34.90, but I still haven't received it. Could you please "
        "process the refund?",
    ),
]


def test_scenarios_file_holds_the_four_assignment_requests_unchanged() -> None:
    scenarios = json.loads(DEFAULT_SCENARIOS.read_text(encoding="utf-8"))

    actual = [(s["scenario_id"], s["authenticated_customer_id"], s["message"]) for s in scenarios]
    assert actual == ASSIGNMENT_REQUESTS
