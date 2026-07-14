-- Staging: 1:1 with raw order_items. Normalizes the deprecated product name
-- ("Comet Mug" -> "Comet Mug V2") so downstream models never see the old label.
create or replace view stg_order_items as
select
    oi.order_item_id,
    oi.order_id,
    oi.product_id,
    case
        when oi.product_name_at_purchase = 'Comet Mug' then 'Comet Mug V2'
        else oi.product_name_at_purchase
    end as product_name,
    oi.quantity,
    oi.unit_price,
    oi.quantity * oi.unit_price as line_amount
from raw_order_items oi;