import populate_db_and_json
import helper
import sqlite3

DB='positionmanager.db'
# populate initial positions
populate_db_and_json.populate_db_and_write_json(db_path=DB, json_path='cl_positions.json')
# ensure strategy exists
helper.create_custom_strategy_intraproduct('1mo spread', [1, -1], db_path=DB)

# apply hedge: user example: Z25:+3, F26:-3 (use years consistent with DB)
base, hedged_name, hedged_lots = helper.implement_hedge('CL', ['outright','outright'], ['Z25','F26'], [3, -3], db_path=DB)
print('result:', base, hedged_name, hedged_lots)

# Inspect cl_positions for Z25 and F26
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("PRAGMA table_info('cl_positions')")
cols = [r[1] for r in cur.fetchall()]
print('cols:', cols)
cur.execute("SELECT contract, lots, outright, \"1mo spread\", \"outright\" FROM cl_positions WHERE contract IN ('Z25','F26') ORDER BY contract")
for row in cur.fetchall():
    print(row)
conn.close()
