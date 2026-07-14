-- CANONICAL: fct_order_items
-- Grain: one row per order line item.
-- Standard hygiene filter (is_test = false) is applied HERE so every
-- downstream consumer inherits it automatically instead of re-deriving it.
create or replace view fct_order_items as
select
    oi.order_item_id,
    oi.order_id,
    o.customer_id,
    o.order_date,
    o.status,
    oi.product_id,
    oi.product_name,
    oi.quantity,
    oi.unit_price,
    oi.line_amount
from stg_order_items oi
join stg_orders o on oi.order_id = o.order_id
where o.is_test = false;