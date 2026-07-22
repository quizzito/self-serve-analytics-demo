
  
  create view "warehouse"."main"."stg_refunds__dbt_tmp" as (
    select
    refund_id,
    order_id,
    cast(refund_date as date) as refund_date,
    refund_amount,
    reason
from "warehouse"."main"."raw_refunds"
  );
