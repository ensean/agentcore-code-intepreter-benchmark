# case: csv_gen  step 1  exitCode=0  executionTime=1.34s

import pandas as pd, numpy as np
rng=np.random.default_rng(42); n=10000
geo={"North America":["United States","Canada","Mexico"],"Europe":["Germany","France","United Kingdom","Spain","Italy"],
"Asia Pacific":["Japan","Australia","India","Singapore"],"Latin America":["Brazil","Argentina","Chile"]}
prods={"Electronics":{"Wireless Earbuds":79.99,"Smartphone":699.0,"Laptop":1199.0,"Smartwatch":249.0,"Bluetooth Speaker":59.99},
"Home & Kitchen":{"Coffee Maker":89.99,"Blender":49.99,"Cookware Set":129.0,"Desk Lamp":34.99},
"Clothing":{"T-Shirt":19.99,"Jeans":54.99,"Running Shoes":109.0,"Winter Jacket":149.0},
"Books":{"Novel":14.99,"Cookbook":24.99,"Textbook":89.0},
"Sports":{"Yoga Mat":29.99,"Dumbbell Set":79.0,"Tennis Racket":119.0}}
regions=rng.choice(list(geo),n,p=[.4,.3,.2,.1])
countries=[rng.choice(geo[r]) for r in regions]
plist=[(c,p,pr) for c,d in prods.items() for p,pr in d.items()]
idx=rng.integers(0,len(plist),n)
cat=[plist[i][0] for i in idx]; prod=[plist[i][1] for i in idx]
base=np.array([plist[i][2] for i in idx])
price=np.round(base*rng.uniform(0.9,1.1,n),2)
qty=np.where(base>500,rng.choice([1,2],n,p=[.85,.15]),rng.choice(range(1,7),n,p=[.45,.25,.12,.08,.06,.04]))
disc=rng.choice([0,0.05,0.1,0.15,0.2,0.25],n,p=[.5,.15,.15,.1,.06,.04])
dates=pd.Timestamp("2025-01-01")+pd.to_timedelta(rng.integers(0,365,n),unit="D")
df=pd.DataFrame({"order_id":[f"ORD-{100001+i}" for i in range(n)],"order_date":dates,"region":regions,"country":countries,
"product":prod,"category":cat,"quantity":qty,"unit_price":price,"discount":disc})
df=df.sort_values("order_date",kind="stable").reset_index(drop=True); df["order_id"]=[f"ORD-{100001+i}" for i in range(n)]
df["order_date"]=df.order_date.dt.strftime("%Y-%m-%d")
df["revenue"]=np.round(df.quantity*df.unit_price*(1-df.discount),2)
df.to_csv("orders.csv",index=False)
d=pd.read_csv("orders.csv")
print(len(d)); print(list(d.columns)); print(d.head(3).to_string())
print(d.order_date.min(),d.order_date.max(),(abs(d.quantity*d.unit_price*(1-d.discount)-d.revenue)<=0.005).all(),d.isna().sum().sum())
