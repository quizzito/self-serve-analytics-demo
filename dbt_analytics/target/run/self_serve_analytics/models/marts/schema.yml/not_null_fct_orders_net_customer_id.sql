
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select customer_id
from "warehouse"."main"."fct_orders_net"
where customer_id is null



  
  
      
    ) dbt_internal_test