
  
  create view "warehouse"."main"."stg_orders__dbt_tmp" as (
    select
    order_id,
    customer_id,
    cast(order_date as date) as order_date,
    status,
    cast(is_test as boolean) as is_test
from "warehouse"."main"."raw_orders"
  );
