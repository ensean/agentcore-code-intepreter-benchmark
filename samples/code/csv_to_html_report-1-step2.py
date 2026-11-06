# case: csv_to_html_report  step 2  exitCode=0  executionTime=0.05s
raw = pd.read_csv("sales.csv", keep_default_na=False, dtype=str)
print(raw.region.value_counts())
print((raw=="").sum().sum())
d = pd.to_datetime(df.order_date, errors='coerce'); print(d.isna().sum(), d.min(), d.max())
calc=(df.quantity*df.unit_price*(1-df.discount)).round(2); print((calc-df.revenue).abs().max())
print(df.order_id.duplicated().sum())