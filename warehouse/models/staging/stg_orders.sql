-- Staging: 1:1 with raw orders, light typing only. No filters, no business logic.
create or replace view stg_orders as
select
    order_id,
    customer_id,
    cast(order_date as date) as order_date,
    status,
    cast(is_test as boolean) as is_test
from raw_orders;