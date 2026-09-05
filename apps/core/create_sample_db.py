import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone

def create_db():
    db_path = Path(__file__).parent.parent / "data" / "sample.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create Customers
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        segment TEXT NOT NULL,
        created_at DATETIME NOT NULL,
        country TEXT NOT NULL
    )
    """)
    
    # Create Products
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        unit_price REAL NOT NULL,
        is_active BOOLEAN NOT NULL
    )
    """)
    
    # Create Orders
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY,
        customer_id INTEGER NOT NULL,
        ordered_at DATETIME NOT NULL,
        region TEXT NOT NULL,
        total_amount REAL NOT NULL,
        status TEXT NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customers (id)
    )
    """)
    
    conn.commit()
    conn.close()
    print(f"Sample database created at: {db_path}")

if __name__ == "__main__":
    create_db()
