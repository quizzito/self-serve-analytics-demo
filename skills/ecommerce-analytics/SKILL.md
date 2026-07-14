---
name: ecommerce-analytics
version: 1.0.0
description: "IF the user asks to query the e-commerce warehouse for any
  revenue, order, refund, or customer question — THEN invoke this skill.
  DO NOT invoke for warehouse schema changes, pipeline debugging, or
  questions with no data-warehouse component."
---

# E-commerce Warehouse Skill Instructions

## Description
Single source of truth for querying the demo e-commerce warehouse
(`warehouse/warehouse.duckdb`). Act as a data analyst: give a governed,
provenance-tagged answer, not just a query result.

**Out-of-scope decisions**: pricing changes, refund policy, marketing spend
allocation → surface the data only, state "decision is [owning team]'s
call", do not author a recommendation.

## Executing queries
Priority:
1. Semantic layer (`warehouse/semantic_layer/metrics.yml`) — REQUIRED first step
2. Raw SQL against canonical marts (`warehouse/models/marts/*.sql`) — fallback only
3. Raw staging/source tables — never query directly; if you think you need to,
   the semantic layer or a mart is missing coverage — say so instead of guessing

---

# Semantic Layer (REQUIRED first step)

The governed semantic layer in `metrics.yml` is the mandatory default path
for every revenue/order/customer/refund question. Raw SQL against marts is
the fallback, used only after the semantic layer is shown not to cover the ask.

## Required workflow
1. **Load** — read `warehouse/semantic_layer/metrics.yml`.
2. **Discover** — match the user's term to a `metrics:` entry or its
   `aliases`. Always check `segments:` too — hand-rolled filters for
   "real customers" or "completed orders" are the dominant wrong-answer
   mode in this warehouse.
3. **Compile + run** — take the metric's `sql` + `source_model`, add the
   requested `dimensions:` grouping/filtering, execute against
   `warehouse.duckdb`.
4. **Fallback** — only if no metric covers the question, or a genuinely new
   cut is needed, write raw SQL against `warehouse/models/marts/*.sql`
   (never against `stg_*` or `raw_*`).

> **Don't bail to raw SQL just because...**
> - "it needs a date filter" → every metric already supports `default_grain`
>   filtering, this is not a reason to hand-roll SQL
> - "it needs a join to products" → see `dimensions.product_category`, the
>   join is documented, not a blocker
> - "it's a simple count" → simple is exactly when hand-rolled SQL silently
>   forgets the `is_test`/`is_real_customer` hygiene filters that are baked
>   into the canonical marts

### Date windows — decide before you query
- **"Last N days"** = trailing N days from `max(order_date)` in
  `fct_orders_net`, NOT from today's wall-clock date (data has a fixed
  snapshot in this demo).
- **"This month" / "last month"** = the full calendar month, not trailing-30.
- If the user doesn't specify a window, ask, or state the default you used
  in the provenance footer.

---

# PART 1: MUST KNOW (Read First for Every Request)

## Quick Start Workflow
1. Check for red flags: PII requests (raw customer emails/PII) → do not
   return raw values, aggregate only.
2. Clarify the request if the metric/segment/window is ambiguous.
3. Check `warehouse/semantic_layer/metrics.yml` for an existing metric.
4. If no coverage, check `references/` for the right canonical mart.
5. Execute the query.
6. Deliver the answer with the provenance footer (below). Separate
   observations ("net revenue was $X") from interpretation ("this suggests Y").

## Business Context

### Entity Disambiguation (MUST CLARIFY)
- **"Revenue"** almost always means `net_revenue` (after refunds), not
  `gross_revenue`. If the user says "revenue" with no qualifier, use
  `net_revenue` and note that choice in the footer.
- **"Customers" / "users"** → use `dim_customers.is_real_customer = true`
  (excludes disposable-email signups) unless the user explicitly asks for
  raw signups including throwaway accounts.
- **"Orders"** → `fct_orders_net` already excludes test + cancelled orders.
  Don't re-derive this filter from raw tables.

### Business Terminology
- **"Comet Mug"** is a deprecated name. The current product is
  **"Comet Mug V2"**. Historical raw order-line data (`raw_order_items`)
  still contains the old label on pre-2026-01-01 rows; `stg_order_items`
  already normalizes this. Never query
  `raw_order_items.product_name_at_purchase` directly for anything
  product-name-related — use `product_name` from `stg_order_items` /
  `fct_order_items` instead.

### Data Integrity Requirements
- NEVER invent columns, tables, or numbers not present in the warehouse.
- ALWAYS use safe division (`nullif(denominator, 0)`).
- ALWAYS state the date window and which segment/hygiene filters were applied.

---

# PART 2: HOW TO DO (Follow During Execution)

## Technical Execution Guide
- Connect: `duckdb.connect('warehouse/warehouse.duckdb', read_only=True)`
- Prefer querying views in `models/marts/` over raw tables.
- PII protection: never return individual customer emails or raw PII;
  aggregate first.

## Analysis Best Practices
1. Clarify the ask before querying (metric, segment, window).
2. Show your work: which metric/segment was used, and why.
3. Clarify denominators for any rate/ratio.
4. Connect the number to business impact only if asked — otherwise, just
   report the observation.
5. **Report with provenance** — every answer ends with a footer:

   > **Source:** [semantic layer | canonical mart | raw exploration] ·
   > **Metric/Segment used:** [name] · **Window:** [date range] ·
   > **Freshness:** [max(order_date) in the data] · **Confidence:** [high
   > if semantic layer, medium if canonical mart, low if raw exploration]

---

# PART 3: DATA REFERENCES

## Knowledge Base Navigation
### Orders & revenue → `references/orders.md`
- Use for: revenue, GMV, AOV, refunds, order counts, order status questions
- Key models: `fct_orders_net`, `fct_order_items`

### Customers → `references/customers.md`
- Use for: active/real customer counts, signups, cohort/segment questions
- Key models: `dim_customers`

## Troubleshooting
- **Metric not in `metrics.yml`?** Check `references/` for the right mart
  before writing raw SQL — don't guess at a join.
- **Numbers don't match a dashboard?** Check `freshness` — the dashboard
  and your query may be reading different snapshot dates.
- **Two tables look similar?** `raw_*` and `stg_*` are never the canonical
  answer. Only `fct_*` / `dim_*` in `models/marts/` are governed.