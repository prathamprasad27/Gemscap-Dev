import sqlite3
import populate_db_and_json
import helper

DB='positionmanager.db'
# ensure clean population
populate_db_and_json.populate_db_and_write_json(db_path=DB, json_path='cl_positions.json')

# ensure strategies inserted by notebook generator
# (populate_db_and_write_json does not insert custom_strategies, so run generator from helper)

# create a small set of strategies we will use
helper.create_custom_strategy_intraproduct('1mo spread', [1, -1], db_path=DB)
helper.create_custom_strategy_intraproduct('1mo fly', [1, -2, 1], db_path=DB)

# read available contracts from cl_positions
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT contract FROM cl_positions ORDER BY contract")
contracts = [r[0] for r in cur.fetchall()]
conn.close()

print('Contracts:', contracts[:6])

# Search for two spreads (same structure name) with starting indices 0..len-3
found = []
for i in range(len(contracts)-1):
    for j in range(len(contracts)-1):
        # set 1 lot each, sign choices -2..2 to allow negatives
        for n1 in [1, -1, 2, -2]:
            for n2 in [1, -1, 2, -2]:
                s1 = '1mo spread'
                s2 = '1mo spread'
                start1 = contracts[i]
                start2 = contracts[j]
                try:
                    # compute aggregated outrights
                    final_contracts, final_lots = helper.unhedge_structure_into_outrights([s1, s2], [start1, start2], [n1, n2], db_path=DB)
                except Exception as e:
                    # missing strategy etc
                    continue

                # factorized check via helper. Try to see if these final_lots match the fly pattern
                try:
                    hedged_name, multiplier = helper.hedge_outrights(final_contracts, final_lots, db_path=DB)
                except Exception:
                    continue

                if hedged_name == '1mo fly':
                    print('Found candidate:', (start1, n1), (start2, n2), '->', final_contracts, final_lots, 'mult', multiplier)
                    found.append((start1, n1, start2, n2, final_contracts, final_lots, multiplier))

print('Total candidates found:', len(found))

# If found, apply implement_hedge for the first candidate and inspect cl_positions
if not found:
    print('No candidate pairs created a 1mo fly with this search.')
else:
    start1, n1, start2, n2, final_contracts, final_lots, multiplier = found[0]
    print('\nApplying implement_hedge on candidate:', start1, n1, start2, n2)
    base, hedged_name, hedged_lots = helper.implement_hedge('CL', [s1, s2], [start1, start2], [n1, n2], db_path=DB)
    print('implement_hedge returned:', base, hedged_name, hedged_lots)

    # inspect affected contracts and structure columns
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info('cl_positions')").fetchall()]
    print('cols:', cols)
    for c in final_contracts:
        cur.execute(f"SELECT contract, lots, outright, \"1mo fly\", \"1mo spread\" FROM cl_positions WHERE contract = ?", (c,))
        print(cur.fetchone())
    conn.close()
