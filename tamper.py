import sqlite3
conn = sqlite3.connect("data/vaas.db")
row = conn.execute("SELECT MAX(id) FROM access_log").fetchone()[0]
conn.execute("UPDATE access_log SET plate_number='XX-FAKE-00' WHERE id=?", (row,))
conn.commit()
print(f"Tampered row id={row}.")
