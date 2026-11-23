# Brief

1. Task: build a small AI-assisted support capability for an ecommerce store; each request is a message plus an already-authenticated customer ID, and the solution may read commerce data and issue refunds.
2. The model may be mocked (a paid API earns no credit), but the mock boundary must be representative of how a real model would be used.
3. Mock environment (scaffolding only): loads immutable seed customers/orders, keeps runtime changes in memory, restart restores seed state, offers temporary storage for refund records and a way to clear it.
4. The mock env must not define refund schema, lifecycle, approval, confirmation or authorization rules, and must not encode how the example requests are handled.
5. Mock env smoke checks are limited to: seed loads, runtime data store/read, runtime state clears, seed files unchanged.
6. Four example requests (order location, partial refund for a broken item, another customer's order, a refund claim with a wrong amount) are illustrative and must not be hard-coded.
7. The solution must be easy to run against the example requests; incomplete work is acceptable if stated clearly; do not optimise for quantity of code.
8. Deliverables: one ZIP of the project (`firstname-lastname-ai-systems.zip`) with implementation, README, mock/data files and raw Claude Code transcripts; no secrets, caches or build artifacts.
9. README sections: how to run, what was implemented, assumptions, what was deliberately left incomplete, what comes next.
10. Time limit: about four hours total, including setup, README, transcripts and packaging; Claude Code is the only AI assistant allowed.
