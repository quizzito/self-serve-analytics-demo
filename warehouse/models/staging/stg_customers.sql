-- Staging: 1:1 with raw customers. Adds is_internal_or_disposable flag used
-- by the canonical "real customer" hygiene filter downstream.
create or replace view stg_customers as
select
    customer_id,
    email_domain,
    cast(signup_date as date) as signup_date,
    country,
    cast(marketing_opt_in as boolean) as marketing_opt_in,
    email_domain in ('mailinator.com', 'tempmail.com') as is_disposable_email
from raw_customers;