"""
Builds warehouse.duckdb from the raw CSVs + the staging/marts SQL models.

raw -> staging (light typing) -> marts (canonical, governed, single source
of truth). Everything downstream reads only from the marts layer.

Run: python3 load_warehouse.py
"""
import glob
import os
import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "..", "data", "raw")
DB_PATH = os.path.join(HERE, "warehouse.duckdb")

RAW_TABLES = {
    "raw_customers": "customers.csv",
    "raw_orders": "orders.csv",
    "raw_order_items": "order_items.csv",
    "raw_products": "products.csv",
    "raw_refunds": "refunds.csv",
}


def run():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = duckdb.connect(DB_PATH)

    for table, csv_file in RAW_TABLES.items():
        path = os.path.join(RAW_DIR, csv_file)
        con.execute(f"create or replace table {table} as select * from read_csv_auto('{path}')")
        print(f"loaded raw table: {table}")

    for layer in ["staging", "marts"]:
        sql_files = sorted(glob.glob(os.path.join(HERE, "models", layer, "*.sql")))
        for f in sql_files:
            with open(f) as fh:
                sql = fh.read()
            con.execute(sql)
            print(f"built model: {os.path.basename(f)}")

    check = con.execute("""
        select round(sum(net_order_amount), 2) as net_revenue_last_30d
        from fct_orders_net
        where order_date > (select max(order_date) from fct_orders_net) - interval 30 day
    """).fetchone()
    print(f"\nsanity check - net revenue, trailing 30d from max order_date: {check[0]}")

    con.close()
    print(f"\nwarehouse built at {DB_PATH}")


if __name__ == "__main__":
    run()