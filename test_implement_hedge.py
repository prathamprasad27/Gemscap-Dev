import populate_db_and_json
import helper
import sqlite3

DB='positionmanager.db'
# ensure cl_positions exists
populate_db_and_json.populate_db_and_write_json(db_path=DB, json_path='cl_positions.json')

# create a sample strategy: simple 2-month spread [1, -1]
helper.create_custom_strategy_intraproduct('TEST_SPREAD', [1, -1], db_path=DB)

# apply hedge: start at Z25 for 1 lot
res = helper.implement_hedge('CL', ['TEST_SPREAD'], ['Z25'], [1], db_path=DB)
print('implement_hedge returned:', res)

# Inspect resulting table
conn = sqlite3.connect(DB)
cur = conn.cursor()
# table chosen by helper is 'cl_structures' or existing candidate
for t in ['cl_structures', 'CL_positions', 'CL_structures', 'cl_positions']:
    try:
        print('\nPRAGMA table_info(%s)' % t)
        for r in cur.execute(f"PRAGMA table_info('{t}')").fetchall():
            print(' ', r)
        print('Rows from', t)
        for r in cur.execute(f"SELECT * FROM '{t}' LIMIT 10").fetchall():
            print('  ', r)
    except Exception as e:
        print('  Error inspecting', t, e)

conn.close()