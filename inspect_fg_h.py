import sqlite3
db='c:\\positionmanager\\positionmanager.db'
conn=sqlite3.connect(db)
cur=conn.cursor()
for c in ['F26','G26','H26']:
    row=cur.execute('SELECT * FROM cl_positions WHERE contract=?',(c,)).fetchone()
    print(row)
conn.close()
