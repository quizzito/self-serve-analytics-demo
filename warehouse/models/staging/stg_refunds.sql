-- Staging: 1:1 with raw refunds.
create or replace view stg_refunds as
select
    refund_id,
    order_id,
    cast(refund_date as date) as refund_date,
    refund_amount,
    reason
from raw_refunds;