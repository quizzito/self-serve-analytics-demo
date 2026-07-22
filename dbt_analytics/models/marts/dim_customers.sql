select
    c.customer_id,
    c.signup_date,
    c.country,
    c.email_domain,
    c.marketing_opt_in,
    c.is_disposable_email,
    not c.is_disposable_email as is_real_customer
from {{ ref('stg_customers') }} c