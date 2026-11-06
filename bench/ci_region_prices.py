"""List AgentCore Code Interpreter On-Demand prices in every region (AWS Price List API, profile test)."""
from __future__ import annotations

import collections
import json
import os

import boto3

pricing = boto3.Session(profile_name=os.environ.get("AWS_PROFILE", "test")).client("pricing", region_name="us-east-1")
rows: dict = collections.defaultdict(dict)
for page in pricing.get_paginator("get_products").paginate(ServiceCode="AmazonBedrockAgentCore"):
    for item in page["PriceList"]:
        p = json.loads(item)
        a = p["product"]["attributes"]
        ut = a.get("usagetype", "")
        if "CodeInterpreter" not in ut:
            continue
        kind = ut.split(":")[-1]
        for term in p["terms"].get("OnDemand", {}).values():
            for dim in term["priceDimensions"].values():
                cur, val = next(iter(dim["pricePerUnit"].items()))
                rows[(a.get("regionCode"), a.get("location"))][kind] = f"{float(val):g} {cur}"

for (code, loc), v in sorted(rows.items(), key=lambda x: (x[1].get("vCPU", ""), x[0][0])):
    print(f"{code:16} {loc:34} vCPU={v.get('vCPU')}  Memory={v.get('Memory')}")
print(len(rows), "regions")
