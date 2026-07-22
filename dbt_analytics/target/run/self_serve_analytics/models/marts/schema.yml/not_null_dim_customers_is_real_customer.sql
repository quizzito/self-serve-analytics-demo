
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select is_real_customer
from "warehouse"."main"."dim_customers"
where is_real_customer is null



  
  
      
    ) dbt_internal_test