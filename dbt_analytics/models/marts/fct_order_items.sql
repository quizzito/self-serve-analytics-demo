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
from {{ ref('stg_order_items') }} oi
join {{ ref('stg_orders') }} o on oi.order_id = o.order_id
where o.is_test = false