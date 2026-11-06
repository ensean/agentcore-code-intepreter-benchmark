# case: csv_to_html_report  step 3  exitCode=0  executionTime=1.98s
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, base64, io, html
df = pd.read_csv("sales.csv", keep_default_na=False, na_values=[""])
df["order_date"]=pd.to_datetime(df.order_date)
df["month"]=df.order_date.dt.to_period("M").astype(str)

def b64(fig):
    buf=io.BytesIO(); fig.savefig(buf,format="png",dpi=110,bbox_inches="tight"); plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()

tot=df.revenue.sum(); orders=df.order_id.nunique(); aov=tot/orders
mr=df.pivot_table(index="month",columns="region",values="revenue",aggfunc="sum").fillna(0)
mr["Total"]=mr.sum(axis=1)
fig,ax=plt.subplots(figsize=(10,4.5))
for r in mr.columns.drop("Total"): ax.plot(mr.index,mr[r],marker="o",label=r)
ax.set_title("Monthly Revenue by Region"); ax.set_ylabel("Revenue"); ax.legend(); ax.grid(alpha=.3)
ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}")); plt.xticks(rotation=45)
c1=b64(fig)

tp=df.groupby("product").agg(revenue=("revenue","sum"),orders=("order_id","count"),units=("quantity","sum")).nlargest(10,"revenue")
tp["share"]=tp.revenue/tot
fig,ax=plt.subplots(figsize=(9,4.5)); ax.barh(tp.index[::-1],tp.revenue[::-1],color="#3b6ea5")
ax.set_title("Top 10 Products by Revenue"); ax.xaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
c2=b64(fig)

cat=df.groupby("category").revenue.sum().sort_values(ascending=False)
fig,ax=plt.subplots(figsize=(6,6)); ax.pie(cat,labels=cat.index,autopct="%1.1f%%",startangle=90,wedgeprops=dict(edgecolor="white"))
ax.set_title("Revenue Share by Category"); c3=b64(fig)

fmt=lambda x:f"{x:,.2f}"
t1=mr.to_html(float_format=fmt,classes="t",border=0)
t2=tp.assign(share=tp.share.map("{:.2%}".format)).to_html(formatters={"revenue":fmt},classes="t",border=0)
t3=cat.to_frame().assign(share=(cat/tot).map("{:.2%}".format)).to_html(formatters={"revenue":fmt},classes="t",border=0)

page=f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Sales Report 2025</title><style>
body{{font-family:Arial,sans-serif;max-width:1100px;margin:30px auto;color:#222;background:#f7f8fa;padding:0 20px}}
h1{{color:#1f3b5c}} h2{{border-bottom:2px solid #3b6ea5;padding-bottom:4px;color:#1f3b5c;margin-top:40px}}
.kpis{{display:flex;gap:20px}} .kpi{{flex:1;background:#fff;border-radius:8px;padding:18px;box-shadow:0 1px 4px rgba(0,0,0,.1);text-align:center}}
.kpi .v{{font-size:28px;font-weight:bold;color:#3b6ea5}} .kpi .l{{color:#666;font-size:14px}}
table.t{{border-collapse:collapse;background:#fff;font-size:13px;margin:10px 0}} .t th,.t td{{padding:6px 10px;border:1px solid #ddd;text-align:right}}
.t thead th{{background:#3b6ea5;color:#fff}} .t tbody tr:nth-child(even){{background:#f0f4f9}}
img{{max-width:100%;background:#fff;border-radius:6px}} .note{{color:#666;font-size:13px}}
</style></head><body>
<h1>Sales Report</h1><p class="note">Source: sales.csv · {len(df):,} rows · {df.order_date.min():%d %b %Y} – {df.order_date.max():%d %b %Y}. Region code “NA” = North America.</p>
<h2>KPI Summary</h2><div class="kpis">
<div class="kpi"><div class="v">{tot:,.2f}</div><div class="l">Total Revenue</div></div>
<div class="kpi"><div class="v">{orders:,}</div><div class="l">Orders</div></div>
<div class="kpi"><div class="v">{aov:,.2f}</div><div class="l">Average Order Value</div></div></div>
<h2>Monthly Revenue by Region</h2><img src="data:image/png;base64,{c1}">{t1}
<h2>Top 10 Products by Revenue</h2><img src="data:image/png;base64,{c2}">{t2}
<h2>Category Revenue Share</h2><img src="data:image/png;base64,{c3}" style="max-width:500px">{t3}
</body></html>"""
open("report.html","w",encoding="utf-8").write(page)
print(tot,orders,aov); print(mr.round(0)); print(tp.round(2)); print((cat/tot).round(4))
import os,re; print(os.path.getsize("report.html"), len(re.findall("data:image/png;base64",page)), "src=\"http" in page)