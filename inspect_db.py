import sqlite3

DB='positionmanager.db'
conn=sqlite3.connect(DB)
cur=conn.cursor()
print('Tables:')
for r in cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall():
    print(r[0])
    print('  SQL:', r[1])

for t in ['custom_strategies', 'cl_positions', 'CL_positions', 'cl_positions', 'cl_positions']:
    try:
        print('\nPRAGMA table_info({}):'.format(t))
        for r in cur.execute(f"PRAGMA table_info('{t}')").fetchall():
            print('  ', r)
    except Exception as e:
        print('  Error for', t, e)

conn.close()