import pandas as pd

token = pd.read_csv("output/token.csv", sep="\t", encoding="utf-8")
set(token.misc_id)
