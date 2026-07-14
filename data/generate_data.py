"""
Generates dummy raw data for the self-serve analytics demo.

Deliberately includes the kind of messiness real warehouses have:
- a renamed product ("Comet Mug" -> "Comet Mug V2") where old rows still
  carry the old name
- some customers signed up with disposable/free-email domains that should
  be excluded from "real" user counts
- some orders are test orders (is_test=1) that must be filtered out
- refunds live in a separate raw table, not yet joined/aggregated anywhere

Run: python3 generate_data.py
Writes CSVs to ./raw/
"""
import csv
import random
import os
from datetime import datetime, timedelta

random.seed(42)
OUT = "raw"
os.makedirs(OUT, exist_ok=True)

SNAPSHOT_DATE = datetime(2026, 7, 1)  # pin eval ground truth to this date

FREE_EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "hotmail.com", "mailinator.com", "tempmail.com"]
CUSTOM_DOMAINS = ["acmeco.com", "anthropic.com", "initech.com", "globex.com", "widgets.io"]

PRODUCTS = [
    (1, "Comet Mug V2", "Home", 18.00),
    (2, "Nebula Backpack", "Bags", 64.00),
    (3, "Starlight Notebook", "Stationery", 12.50),
    (4, "Orbit Water Bottle", "Home", 22.00),
    (5, "Lunar Hoodie", "Apparel", 48.00),
]

N_CUSTOMERS = 400
N_ORDERS = 1800

# ---------- customers.csv ----------
customers = []
for cid in range(1, N_CUSTOMERS + 1):
    is_free_email = random.random() < 0.35
    domain = random.choice(FREE_EMAIL_DOMAINS) if is_free_email else random.choice(CUSTOM_DOMAINS)
    signup_days_ago = random.randint(1, 540)
    signup_date = SNAPSHOT_DATE - timedelta(days=signup_days_ago)
    customers.append({
        "customer_id": cid,
        "email_domain": domain,
        "signup_date": signup_date.strftime("%Y-%m-%d"),
        "country": random.choice(["US", "US", "US", "CA", "UK", "DE", "AU"]),
        "marketing_opt_in": random.random() < 0.6,
    })

with open(f"{OUT}/customers.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=customers[0].keys())
    w.writeheader()
    w.writerows(customers)

# ---------- products.csv ----------
with open(f"{OUT}/products.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["product_id", "product_name", "category", "unit_price"])
    for p in PRODUCTS:
        w.writerow(p)

# ---------- orders.csv + order_items.csv ----------
orders = []
order_items = []
item_id = 1
for oid in range(1, N_ORDERS + 1):
    cust = random.randint(1, N_CUSTOMERS)
    days_ago = random.randint(0, 365)
    order_date = SNAPSHOT_DATE - timedelta(days=days_ago)
    is_test = random.random() < 0.02  # 2% test orders, must be excluded
    status = random.choices(
        ["completed", "completed", "completed", "cancelled", "pending"],
        weights=[70, 10, 10, 7, 3],
    )[0]

    orders.append({
        "order_id": oid,
        "customer_id": cust,
        "order_date": order_date.strftime("%Y-%m-%d"),
        "status": status,
        "is_test": int(is_test),
    })

    n_items = random.randint(1, 3)
    for _ in range(n_items):
        prod = random.choice(PRODUCTS)
        product_id, product_name, category, price = prod
        qty = random.randint(1, 2)
        # simulate the deprecated-name gotcha: orders before 2026-01-01 for
        # product_id 1 were recorded under the OLD name "Comet Mug"
        line_name = product_name
        if product_id == 1 and order_date < datetime(2026, 1, 1):
            line_name = "Comet Mug"
        order_items.append({
            "order_item_id": item_id,
            "order_id": oid,
            "product_id": product_id,
            "product_name_at_purchase": line_name,
            "quantity": qty,
            "unit_price": price,
        })
        item_id += 1

with open(f"{OUT}/orders.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=orders[0].keys())
    w.writeheader()
    w.writerows(orders)

with open(f"{OUT}/order_items.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=order_items[0].keys())
    w.writeheader()
    w.writerows(order_items)

# ---------- refunds.csv (raw, unaggregated - a trap table) ----------
refunds = []
rid = 1
for o in orders:
    if o["status"] == "completed" and random.random() < 0.06:
        refund_date = datetime.strptime(o["order_date"], "%Y-%m-%d") + timedelta(days=random.randint(1, 20))
        if refund_date <= SNAPSHOT_DATE:
            refunds.append({
                "refund_id": rid,
                "order_id": o["order_id"],
                "refund_date": refund_date.strftime("%Y-%m-%d"),
                "refund_amount": round(random.uniform(10, 80), 2),
                "reason": random.choice(["damaged", "wrong_item", "changed_mind", "late_delivery"]),
            })
            rid += 1

with open(f"{OUT}/refunds.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=refunds[0].keys())
    w.writeheader()
    w.writerows(refunds)

print(f"Wrote {len(customers)} customers, {len(orders)} orders, "
      f"{len(order_items)} order_items, {len(refunds)} refunds to ./{OUT}/")
print(f"Snapshot date (pin evals to this): {SNAPSHOT_DATE.strftime('%Y-%m-%d')}")