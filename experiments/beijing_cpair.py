"""Beijing holdout analysis: measured per-line circuity c_pair (input-side,
never touches measured totals) + open-chain TSP fix.

c_pair := median over sampled store pairs (haversine in [0.3,3] km) of
OSRM_driving/haversine. Declared input with sample provenance (spec §2
"声明输入"); does NOT use the ground-truth monthly total.
"""
import json, math, subprocess, time, sys
import numpy as np
import pandas as pd
sys.path.insert(0, "/tmp")
from bjholdout import gcj2wgs

df = pd.read_excel("/tmp/全部.xlsx")
df["客户编码"] = df["客户编码"].astype(str)
bj = df[df["province"].astype(str).str.strip() == "110000"].copy()
rows = json.load(open("/tmp/output/beijing_holdout_v1.json"))

R = 6371.0
def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, a + b)
    h = (math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2)
    return 2*R*math.asin(math.sqrt(h))

def curl(url, tries=3):
    for k in range(tries):
        try:
            o = subprocess.run(["curl", "-s", "--max-time", "60", url],
                               capture_output=True, text=True, timeout=65)
            return json.loads(o.stdout)
        except Exception:
            time.sleep(2 * (k+1))
    return None

out = {}
for r in rows:
    line = r["line"]
    ln = bj[bj["销售编码"] == line]
    sd = ln.groupby("客户编码")[["lng","lat"]].first()
    pts = [gcj2wgs(a, b) for a, b in zip(sd["lng"], sd["lat"])]
    rng = np.random.default_rng(abs(hash(line)) % 2**31)
    samp = [pts[i] for i in rng.choice(len(pts), min(90, len(pts)), replace=False)]
    wp = ";".join(f"{p[0]},{p[1]}" for p in samp)
    d = curl(f"https://router.project-osrm.org/table/v1/driving/{wp}?annotations=distance")
    if not d or d.get("code") != "Ok":
        print(f"{line}: table FAIL"); out[line] = None; continue
    D = np.array(d["distances"])/1000.0
    ratios = []
    n = len(samp)
    for i in range(n):
        for j in range(i+1, n):
            hv = hav(samp[i], samp[j])
            if 0.3 <= hv <= 3.0 and hv > 0:
                ratios.append(D[i, j]/hv)
    c_pair = float(np.median(ratios))
    out[line] = dict(c_pair=round(c_pair, 3), npairs=len(ratios),
                     p25=round(float(np.percentile(ratios,25)),3),
                     p75=round(float(np.percentile(ratios,75)),3))
    print(f"{line:<11} A={r['A_hull']:>7.1f} c_pair={c_pair:.3f} "
          f"(p25={out[line]['p25']}, p75={out[line]['p75']}, n={len(ratios)})", flush=True)

json.dump(out, open("/tmp/output/beijing_cpair.json", "w"), indent=1)

# 重判: 用 c_pair 重新计算两项式 mid 并求 ratio (对已有 meas)
BETA, KAPPA = 0.7124, 0.9531
import numpy as np
r_pure_c, r_two_c = [], []
print(f"\n{'line':<11}{'A_hull':>8}{'c_pair':>7}{'r_two_prior':>12}{'r_two_cpair':>12}{'r_pure_cpair':>13}")
for r in rows:
    cp = out.get(r["line"]) or {}
    c = cp.get("c_pair", 1.22)
    V, K, A = r["V"], r["K"], r["A_hull"]
    mid2c = c*(BETA*math.sqrt(V*A) + KAPPA*math.sqrt(K*A))
    midpc = c*BETA*math.sqrt(V*A)
    r_two_c.append(r["meas_osrm"]/mid2c); r_pure_c.append(r["meas_osrm"]/midpc)
    print(f"{r['line']:<11}{r['A_hull']:>8.1f}{c:>7.3f}{r['r_two_meas']:>12.3f}"
          f"{r['meas_osrm']/mid2c:>12.3f}{r['meas_osrm']/midpc:>13.3f}")
for name, rs in [("pure/c_pair", r_pure_c), ("two/c_pair", r_two_c)]:
    cov = sum(1 for x in rs if 0.75 <= x <= 1.30)
    print(f"\n{name}: median={np.median(rs):.3f} cov[0.75,1.30]={cov}/{len(rs)}")
