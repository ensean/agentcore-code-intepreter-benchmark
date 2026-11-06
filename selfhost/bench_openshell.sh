#!/bin/bash
# OpenShell (Docker driver) cold start / exec / memory benchmark on one EC2 host.
# Usage: ./bench_openshell.sh <n_sequential> <n_concurrent_for_density>
set -uo pipefail
N=${1:-10}
C=${2:-10}
IMG=ci-sandbox:py312
EXTRA=${EXTRA:-}
OUT=${OUT:-results_openshell.jsonl}
IMPORTS="import numpy, pandas, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot"
now() { date +%s.%N; }
dt() { python3 -c "print(round($2-$1,3))"; }

for i in $(seq 1 "$N"); do
  name="cold-$i-$RANDOM"
  t0=$(now)
  openshell sandbox create --name "$name" --from "$IMG" $EXTRA --detach --no-tty -- sleep infinity >/dev/null 2>&1
  t1=$(now)
  openshell sandbox exec -n "$name" --no-tty -- python -c "print(1)" >/dev/null 2>&1 </dev/null
  t2=$(now)
  openshell sandbox exec -n "$name" --no-tty -- python -c "print(1)" >/dev/null 2>&1 </dev/null
  t3=$(now)
  openshell sandbox exec -n "$name" --no-tty -- python -c "$IMPORTS" >/dev/null 2>&1 </dev/null
  t4=$(now)
  openshell sandbox exec -n "$name" --no-tty -- python -c "$IMPORTS" >/dev/null 2>&1 </dev/null
  t5=$(now)
  inproc=$(openshell sandbox exec -n "$name" --no-tty -- python -c "import time;t=time.time();$IMPORTS;print(round(time.time()-t,3))" 2>/dev/null </dev/null | tail -1)
  t6=$(now)
  openshell sandbox delete "$name" >/dev/null 2>&1
  t7=$(now)
  echo "{\"idx\":$i,\"create_s\":$(dt $t0 $t1),\"first_exec_s\":$(dt $t1 $t2),\"time_to_first_result_s\":$(dt $t0 $t2),\"warm_exec_s\":$(dt $t2 $t3),\"import_first_s\":$(dt $t3 $t4),\"import_again_s\":$(dt $t4 $t5),\"import_inprocess_s\":${inproc:-null},\"delete_s\":$(dt $t6 $t7)}" | tee -a "$OUT"
done

# density: C idle sandboxes, then each with pandas+matplotlib loaded in a long-lived python
echo "--- density with $C sandboxes"
free -m | awk 'NR==2{print "host_used_before_MiB="$3}'
for i in $(seq 1 "$C"); do
  openshell sandbox create --name "dens-$i" --from "$IMG" $EXTRA --detach --no-tty -- \
    python -c "$IMPORTS; import time; time.sleep(36000)" >/dev/null 2>&1 &
done
wait
sleep 20
free -m | awk 'NR==2{print "host_used_after_MiB="$3}'
[ -n "${SKIP_DOCKER_STATS:-}" ] || docker stats --no-stream --format "{{.Name}} {{.MemUsage}}" | tee docker_stats.txt; ps -eo rss,comm --sort=-rss | head -15
for i in $(seq 1 "$C"); do openshell sandbox delete "dens-$i" >/dev/null 2>&1 & done
wait
