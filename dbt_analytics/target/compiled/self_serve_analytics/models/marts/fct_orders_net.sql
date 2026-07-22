with gross as (
    select
        order_id,
        customer_id,
        order_date,
        status,
        sum(line_amount) as gross_order_amount
    from "warehouse"."main"."fct_order_items"
    group by 1, 2, 3, 4
),
refunded as (
    select order_id, sum(refund_amount) as refund_amount
    from "warehouse"."main"."stg_refunds"
    group by 1
)
select
    g.order_id,
    g.customer_id,
    g.order_date,
    g.status,
    g.gross_order_amount,
    coalesce(r.refund_amount, 0) as refund_amount,
    g.gross_order_amount - coalesce(r.refund_amount, 0) as net_order_amount
from gross g
left join refunded r on g.order_id = r.order_id
where g.status != 'cancelled'