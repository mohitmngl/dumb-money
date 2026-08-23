"""Rebuild India strings after filter changes."""
from dumbmoney.db import init_all_dbs, ensure_schema, migrate_nulls
from dumbmoney.basket_screener import generate_string_universe

if __name__ == "__main__":
    init_all_dbs()
    ensure_schema("india.db")
    migrate_nulls("india.db")
    count = generate_string_universe("INDIA", force=True)
    print(f"India strings rebuilt: {count}")
