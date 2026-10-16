# Settled order revenue: exposed development task

Question: What is total settled order revenue in USD during the first quarter of
2026? Count each order once, regardless of its number of line items. Amounts are
stored in cents.

The analytical interval is January 1, 2026, 00:00 UTC inclusive through April 1,
2026, 00:00 UTC exclusive. Include orders whose status is `settled` and currency
is `USD`. Sum order amounts at `order_id` grain, then divide cents by 100. A
missing amount in an eligible order prevents a complete revenue answer; the task
must explicitly permit abstention before that answer form is accepted.

The required slot is `settled_revenue_usd`, denominated in USD at order grain.
Any supporting numerical slots must also be explicitly declared in the task.
Snapshot identity and current versus historical semantics form part of the
contract. Result authenticity, claim binding, semantic checks, and independent
correctness are separate properties.

The development family exercises one-to-many joins and repeated order amounts.
Valid approaches include aggregating orders directly, filtering items with an
existence condition, or collapsing item rows to order identities before a join.
Deduplicating amounts alone does not implement distinct order identity.

This card contains public semantics only. Reference answers, faulty-query labels,
and scoring implementation belong to the separate evaluator. This exposed
development fixture is unsuitable for held-out performance claims. The initial
validator runs only fixed SQL authored by the developers and does not establish
an untrusted-query execution or publication security boundary.
