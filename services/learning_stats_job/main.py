#!/usr/bin/env python3
"""
Nightly Strategy Stats Job (Scaffold)
- Reads position_history
- Computes strategy_stats for a lookback window
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor

SQL_PATH = os.path.join(os.path.dirname(__file__), "sql", "compute_strategy_stats.sql")


def load_sql() -> str:
    with open(SQL_PATH, "r", encoding="utf-8") as f:
        return f.read()


def main():
    db_host = os.environ.get("DB_HOST")
    db_port = int(os.environ.get("DB_PORT", "5432"))
    db_name = os.environ.get("DB_NAME")
    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD")
    lookback_days = int(os.environ.get("LOOKBACK_DAYS", "90"))

    if not all([db_host, db_name, db_user, db_password]):
        raise RuntimeError("Missing DB_* environment variables")

    sql = load_sql()

    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
        connect_timeout=10,
    )

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, {"lookback_days": lookback_days})
        conn.commit()

    conn.close()
    print(f"strategy_stats updated (lookback_days={lookback_days})")


if __name__ == "__main__":
    main()
