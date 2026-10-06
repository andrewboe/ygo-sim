"""Print name and type of card ids from the runtime DB. Usage: card_info.py ID [ID...]"""
import os
import sqlite3
import sys

con = sqlite3.connect(os.path.expanduser("~/ygo/run/cards.cdb"))
for cid in map(int, sys.argv[1:]):
    row = con.execute("select t.name, d.type, d.alias from datas d join texts t on t.id = d.id where d.id = ?",
                      (cid,)).fetchone()
    print(cid, row and f"{row[0]}  type={row[1]:#x}  alias={row[2]}")
