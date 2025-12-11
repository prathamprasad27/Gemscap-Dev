import sqlite3
import json

# Month codes used in the notebook
lis_months = ["F","G","H","J","K","M","N","Q","U","V","X","Z"]

def generate_contract_sequence(start_month_idx, start_year, end_month_idx, end_year):
    seq = []
    m = start_month_idx
    y = start_year
    while True:
        seq.append(lis_months[m] + str(y))
        if y == end_year and m == end_month_idx:
            break
        m += 1
        if m == 12:
            m = 0
            y += 1
    return seq

def populate_db_and_write_json(product="CL", db_path="positionmanager.db", json_path=None):
    if json_path is None:
        json_path = f"{product.lower()}_positions.json"
        
    table_name = f"{product}_positions"

    # Generate contracts from Z25 → Z27 (month-by-month)
    start_idx = lis_months.index("Z")
    start_year = 25
    end_idx = lis_months.index("Z")
    end_year = 27

    contracts = generate_contract_sequence(start_idx, start_year, end_idx, end_year)

    # Create an alternating dummy pattern: 3, -5, 3, -5, ...
    lots = [3 if i % 2 == 0 else -5 for i in range(len(contracts))]

    # Create / open sqlite DB and create table
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # For population helper we reset positions to a clean state so initial
    # 'outright' equals 'lots' and there is no leftover data from previous runs.
    cur.execute(f"DROP TABLE IF EXISTS {table_name}")

    # Ensure table exists. If an older schema uses 'Total' column, we'll preserve it
    cur.execute(f"CREATE TABLE IF NOT EXISTS {table_name} (contract TEXT PRIMARY KEY)")

    # Inspect columns and ensure 'lots' column exists (migrate from 'Total' if present)
    cur.execute(f"PRAGMA table_info('{table_name}')")
    existing_cols = [r[1] for r in cur.fetchall()]
    if 'lots' not in existing_cols:
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN lots INTEGER DEFAULT 0")
        # If an old 'Total' column exists, copy its values into 'lots'
        if 'Total' in existing_cols:
            cur.execute(f"UPDATE {table_name} SET lots = COALESCE(Total, 0)")
        conn.commit()


    # Insert or replace rows (write into 'lots')
    for contract, lot in zip(contracts, lots):
        cur.execute(
            f"INSERT OR REPLACE INTO {table_name} (contract, lots) VALUES (?, ?)",
            (contract, lot)
        )

    conn.commit()

    # Ensure `outright` column exists and initialize it to `lots` for initial parity
    cur.execute(f"PRAGMA table_info('{table_name}')")
    cols = [r[1] for r in cur.fetchall()]
    if 'outright' not in cols:
        cur.execute(f'ALTER TABLE {table_name} ADD COLUMN "outright" INTEGER DEFAULT 0')
        cur.execute(f'UPDATE {table_name} SET outright = COALESCE(lots, 0)')
        conn.commit()

    # Read back and write JSON file for the frontend
    cur.execute(f"SELECT contract, lots FROM {table_name} ORDER BY contract")
    rows = cur.fetchall()
    conn.close()

    data = [{"contract": r[0], "lots": r[1]} for r in rows]

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote {len(data)} rows to table '{table_name}' in '{db_path}' and JSON to '{json_path}'")

if __name__ == "__main__":
    populate_db_and_write_json()
