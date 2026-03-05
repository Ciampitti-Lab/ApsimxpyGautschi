import pandas as pd
import sqlite3
import glob

dfs = []

for db in glob.glob("*.db"):
    conn = sqlite3.connect(db)
    dfs.append(pd.read_sql("SELECT * FROM Report", conn))

final = pd.concat(dfs)
final.to_csv("all_results.csv", index=False)