# Orders & Revenue Tables

## Quick Reference
### Business Context
Orders are placed by customers, contain 1+ line items, and may later be
partially or fully refunded. "Revenue" for this business means order value
net of refunds, excluding test traffic and cancelled orders.

### Entity Grain
- `fct_orders_net`: one row per order.
- `fct_order_items`: one row per order line item.

### Standard Hygiene Filter
Every query in this domain must exclude test orders (`is_test = true`) and
cancelled orders (`status = 'cancelled'`). Both are already applied inside
`fct_orders_net` and `fct_order_items` — do not re-derive from raw tables.

## Key Tables

### fct_orders_net (CANONICAL for revenue)
- **Grain**: one row per order_id.
- **Scope/exclusions**: excludes test orders and cancelled orders. Nets
  refunds against gross order value.
- **Usage**: use for net_revenue, gross_revenue, refund_amount, refund_rate,
  order_count, AOV. Do not aggregate revenue from raw_order_items or
  raw_refunds directly — you will double count or miss the test-order filter.

### fct_order_items (CANONICAL for line-item / product-level questions)
- **Grain**: one row per order line item.
- **Scope/exclusions**: excludes test orders. Does NOT exclude cancelled
  orders — filter on `status` explicitly if the question is revenue-related.
- **Usage**: units_sold, product-level breakdowns. Join to `raw_products`
  for category.

### raw_refunds (NOT canonical — do not query directly for revenue)
- **Grain**: one row per refund.
- **Usage**: only for refund-reason breakdowns. For refund *amounts*
  aggregated with revenue, use `fct_orders_net.refund_amount`.

## Gotchas
- "Comet Mug" (old name) vs "Comet Mug V2" (current name) — see SKILL.md
  Business Terminology. Use `product_name` from `stg_order_items` /
  `fct_order_items`, never `raw_order_items.product_name_at_purchase`.
- A "pending" order is included in `fct_order_items` but excluded from
  `fct_orders_net` revenue totals since it hasn't completed.
- Refund lag: a refund can be issued up to ~20 days after the order date —
  "revenue for the last 7 days" will look artificially high vs. the
  eventual net number once refunds land.

## Best Practices / Common Query Patterns
- Revenue over time: `select order_date, sum(net_order_amount) from
  fct_orders_net group by 1 order by 1`
- Top products by units: join `fct_order_items` to `raw_products` on
  `product_id`, group by category or product_name.

## Cross-References
- `references/customers.md` for customer-level joins.