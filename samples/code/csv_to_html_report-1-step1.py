# case: csv_to_html_report  step 1  exitCode=0  executionTime=1.28s
import pandas as pd
df = pd.read_csv("sales.csv")
print(df.shape); print(df.dtypes); print(df.head()); print(df.isna().sum()); print(df.describe(include='all').T)