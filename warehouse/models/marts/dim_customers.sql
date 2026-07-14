-- CANONICAL: dim_customers
-- Grain: one row per customer_id.
-- This is the single governed source for "who is a real customer".
create or replace view dim_customers as
select
    c.customer_id,
    c.signup_date,
    c.country,
    c.email_domain,
    c.marketing_opt_in,
    c.is_disposable_email,
    not c.is_disposable_email as is_real_customer
from stg_customers c;