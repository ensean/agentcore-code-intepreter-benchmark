"""Monthly cost: AgentCore Code Interpreter (measured) vs self-hosted OpenShell on EC2 (modelled).

All inputs below come from this PoC's measurements or the AWS Price List API (ap-northeast-1, On-Demand).
"""
from __future__ import annotations

import math

HOURS = 730
SEC_PER_MONTH = 30 * 86400

# --- AgentCore Code Interpreter, measured mean cost per request (results/summary.json)
CI_PER_REQ = {"csv_gen": 0.000155, "csv_to_html_report": 0.000321, "static_html": 0.000284}
CI_MIX = sum(CI_PER_REQ.values()) / 3

# --- workload shape (measured in the CI benchmark, identical agent loop)
SESSION_S = (22.9 + 51.3 + 60.7) / 3 + 1.0        # mean sandbox lifetime per request + create/delete
VCPU_S_PER_REQ = (2.59 + 4.65 + 2.05) / 3         # active CPU per request

# --- self-hosted node: m8i.large (2 vCPU / 8 GiB), gp3 40 GB
NODE_HR = 0.13671
EBS_MONTH = 40 * 0.096
NODE_MONTH = NODE_HR * HOURS + EBS_MONTH
ALLOC_GIB = 6.0          # 8 GiB minus OS, dockerd, gateway, page cache headroom
CPU_TARGET = 0.6         # keep node CPU <= 60% on average to absorb bursts

MODES = {
    # measured: MicroVM RSS ~254 MiB with pandas+matplotlib loaded; budget 0.5 GiB incl. execution peak
    "OpenShell MicroVM (VM 隔离)": 0.5,
    # measured: container 71 MiB + supervisor 14 MiB; budget 0.25 GiB incl. execution peak
    "OpenShell Docker (容器隔离)": 0.25,
}
PEAK_FACTOR = 3.0        # peak-hour arrival rate / monthly average
HEADROOM = 1.2
MIN_NODES = 2            # two AZs for availability


def per_node_slots(gib_per_sandbox: float) -> int:
    mem_slots = ALLOC_GIB / gib_per_sandbox
    cpu_slots = 2 * CPU_TARGET / (VCPU_S_PER_REQ / SESSION_S)
    return int(min(mem_slots, cpu_slots))


def selfhost_cost(req: int, gib: float) -> tuple:
    lam = req / SEC_PER_MONTH
    slots = per_node_slots(gib)
    peak_conc = lam * PEAK_FACTOR * SESSION_S
    avg_conc = lam * SESSION_S
    fixed_nodes = max(MIN_NODES, math.ceil(peak_conc * HEADROOM / slots))
    auto_node_months = max(MIN_NODES, avg_conc * HEADROOM / slots)
    return slots, peak_conc, fixed_nodes, fixed_nodes * NODE_MONTH, auto_node_months * NODE_MONTH


if __name__ == "__main__":
    print(f"node month = ${NODE_MONTH:.2f}; session {SESSION_S:.1f}s; vCPU-s/req {VCPU_S_PER_REQ:.2f}; CI mix ${CI_MIX:.6f}/req")
    for mode, gib in MODES.items():
        print(f"\n{mode}: slots/node = {per_node_slots(gib)}")
        print(f"{'req/month':>12} {'CI $':>10} {'peak conc':>9} {'nodes':>5} {'self fixed $':>12} {'self autoscale $':>16}")
        for req in [10_000, 100_000, 1_000_000, 10_000_000]:
            slots, pc, n, fixed, auto = selfhost_cost(req, gib)
            print(f"{req:>12,} {CI_MIX*req:>10.2f} {pc:>9.1f} {n:>5} {fixed:>12.2f} {auto:>16.2f}")
    be = MIN_NODES * NODE_MONTH / CI_MIX
    print(f"\nbreak-even vs {MIN_NODES} always-on nodes: {be:,.0f} req/month")
    print(f"single node, no HA: ${NODE_MONTH:.2f}/month -> break-even {NODE_MONTH/CI_MIX:,.0f} req/month")
