
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  -- This test PASSES if it returns ZERO rows.
-- If it ever returns rows, the deprecated "Comet Mug" name (pre-rename)
-- is leaking into a canonical model again, which would cause exactly
-- the undercount bug this project found and fixed early on.

select *
from "warehouse"."main"."fct_order_items"
where product_name = 'Comet Mug'
  
  
      
    ) dbt_internal_test