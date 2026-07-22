
    
    

select
    order_id as unique_field,
    count(*) as n_records

from "warehouse"."main"."fct_orders_net"
where order_id is not null
group by order_id
having count(*) > 1


