select
    customer_id,
    email_domain,
    cast(signup_date as date) as signup_date,
    country,
    cast(marketing_opt_in as boolean) as marketing_opt_in,
    email_domain in ('mailinator.com', 'tempmail.com') as is_disposable_email
from "warehouse"."main"."raw_customers"