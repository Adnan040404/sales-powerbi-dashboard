"""
Exports a star-schema dataset for Power BI from the ETL pipeline's warehouse
(see the sales-data-etl-pipeline repo).

    fact_sales.csv   one row per order line
    dim_date.csv     one row per calendar day (continuous, no gaps)
    dim_product.csv  product -> category

Usage:
    python export_data.py [path/to/sales_warehouse.db]
"""

import os
import sqlite3
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(HERE, "..", "sales-data-cleaning-automation", "output",
                          "sales_warehouse.db")
DB = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
OUT = os.path.join(HERE, "data")
os.makedirs(OUT, exist_ok=True)

CATEGORY = {
    "USB-C Cable": "Accessories", "Wireless Mouse": "Accessories",
    "Mechanical Keyboard": "Accessories", "Laptop Stand": "Accessories",
    "Docking Station": "Accessories", "27-inch Monitor": "Displays",
    "Webcam HD": "Video", "Noise-Cancelling Headphones": "Audio",
    "Bluetooth Speaker": "Audio", "External SSD 1TB": "Storage",
    "Smart LED Lamp": "Home Office", "Ergonomic Chair": "Furniture",
}

conn = sqlite3.connect(DB)
fact = pd.read_sql_query(
    "SELECT order_id, order_date, customer, product, channel, quantity, unit_price, "
    "discount, revenue FROM sales ORDER BY order_date, order_id", conn)
conn.close()

missing = set(fact["product"]) - set(CATEGORY)
if missing:
    raise SystemExit(f"Products without a category: {sorted(missing)}")

fact.to_csv(os.path.join(OUT, "fact_sales.csv"), index=False)

days = pd.date_range(fact["order_date"].min(), fact["order_date"].max(), freq="D")
# extend to full calendar months so month totals and axes look complete
days = pd.date_range(days.min().replace(day=1),
                     (days.max() + pd.offsets.MonthEnd(0)), freq="D")
dim_date = pd.DataFrame({"Date": days})
dim_date["Year"] = dim_date["Date"].dt.year
dim_date["Quarter"] = "Q" + dim_date["Date"].dt.quarter.astype(str)
dim_date["MonthNumber"] = dim_date["Date"].dt.month
dim_date["Month"] = dim_date["Date"].dt.strftime("%b")
dim_date["MonthYear"] = dim_date["Date"].dt.strftime("%b %Y")
dim_date["MonthStart"] = dim_date["Date"].dt.to_period("M").dt.start_time
dim_date["WeekdayNumber"] = dim_date["Date"].dt.dayofweek + 1
dim_date["Weekday"] = dim_date["Date"].dt.strftime("%a")
dim_date["IsWeekend"] = dim_date["WeekdayNumber"] >= 6
dim_date.to_csv(os.path.join(OUT, "dim_date.csv"), index=False, date_format="%Y-%m-%d")

pd.DataFrame(sorted(CATEGORY.items()), columns=["product", "category"]).to_csv(
    os.path.join(OUT, "dim_product.csv"), index=False)

print(f"fact_sales: {len(fact):,} rows | revenue {fact['revenue'].sum():,.2f}")
print(f"dim_date: {len(dim_date)} days ({days.min():%Y-%m-%d} to {days.max():%Y-%m-%d})")
print(f"dim_product: {len(CATEGORY)} products")
