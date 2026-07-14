# Customer Tables

## Quick Reference
### Business Context
A "customer" record is created on signup. Not every signup is a real
person — some are disposable/throwaway-email test signups that should be
excluded from customer counts and cohort analysis.

### Entity Grain
`dim_customers`: one row per customer_id.

### Standard Hygiene Filter
`is_real_customer = true` (excludes `mailinator.com` / `tempmail.com`
domains). Apply this for ANY "how many customers/users" question unless the
user explicitly asks to include disposable signups.

## Key Tables

### dim_customers (CANONICAL)
- **Grain**: one row per customer.
- **Scope/exclusions**: none at the row level — the disposable-email flag
  is a column, not a pre-applied filter, since some legitimate questions
  need the excluded rows too.
- **Usage**: join to `fct_orders_net` on `customer_id` for
  "active customers" (customers with >=1 order in a window).

## Gotchas
- "Active customers" needs BOTH `is_real_customer = true` AND a join to
  `fct_orders_net` filtered to the window.
- Country field is self-reported at signup and not always accurate for
  customers who later moved — treat country cuts as directional.

## Best Practices / Common Query Patterns
- Active customers last 30 days:
```sql
  select count(distinct fo.customer_id)
  from fct_orders_net fo
  join dim_customers dc on fo.customer_id = dc.customer_id
  where dc.is_real_customer = true
    and fo.order_date > (select max(order_date) from fct_orders_net) - interval 30 day
```

## Cross-References
- `references/orders.md` for order/revenue definitions used in "active" joins.