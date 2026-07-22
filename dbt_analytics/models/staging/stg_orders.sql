select
    order_id,
    customer_id,
    cast(order_date as date) as order_date,
    status,
    cast(is_test as boolean) as is_test
from {{ source('raw', 'raw_orders') }}