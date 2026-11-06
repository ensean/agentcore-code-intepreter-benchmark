# case: csv_gen  step 2  exitCode=0  executionTime=0.01s
diff=abs(d.quantity*d.unit_price*(1-d.discount)-d.revenue); print(diff.max(), (diff>0.005+1e-9).sum())