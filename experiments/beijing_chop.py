"""Hop-scale-adaptive circuity on Beijing holdout (c_hop).

c_pair with fixed 0.3-3km window biased toward short hops. The circuity the
BHH term needs is the one experienced by plan edges: sample pairs within
[0.7, 2.5] x lambda, lambda = sqrt(A_hull/n) (nearest-neighbor scale).
Re-evaluate two-term model with measured c_hop.
"""
import json, math, subprocess, time, sys
import numpy as np
import pandas as pd
sys.path.insert(0, "/tmp")
from bjholdout import gcj2wgs

BETA, KAPPA = 0.7124, 0.9531
R = 6371.0

def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, a + b)
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
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

df = pd.read_excel("/tmp/全部.xlsx")
df["客户编码"] = df["客户编码"].astype(str)
bj = df[df["province"].astype(str).str.strip() == "110000"].copy()
rows = json.load(open("/tmp/output/beijing_holdout_v1.json"))

rs_prior, rs_hop = [], []
out = {}
print(f"{'line':<11}{'A/n':>6}{'λ':>6}{'c_prior':>8}{'c_hop':>7}{'r_two_prior':>12}{'r_two_hop':>11}")
for r in rows:
    ln = bj[bj["销售编码"] == r["line"]]
    sd = ln.groupby("客户编码")[["lng", "lat"]].first()
    pts = [gcj2wgs(a, b) for a, b in zip(sd["lng"], sd["lat"])]
    lam = math.sqrt(r["A_hull"] / r["n"])          # NN 尺度 km
    rng = np.random.default_rng(abs(hash(r["line"])) % 2**31)
    samp = [pts[i] for i in rng.choice(len(pts), min(90, len(pts)), replace=False)]
    wp = ";".join(f"{p[0]},{p[1]}" for p in samp)
    d = curl(f"https://router.project-osrm.org/table/v1/driving/{wp}?annotations=distance")
    if not d or d.get("code") != "Ok":
        print(f"{r['line']}: FAIL"); continue
    D = np.array(d["distances"]) / 1000.0
    lo, hi = max(0.3, 0.7*lam), 2.5*lam
    ratios = [D[i, j]/hav(samp[i], samp[j])
              for i in range(len(samp)) for j in range(i+1, len(samp))
              if lo <= hav(samp[i], samp[j]) <= hi]
    if len(ratios) < 30:
        ratios = [D[i, j]/hav(samp[i], samp[j])
                  for i in range(len(samp)) for j in range(i+1, len(samp))
                  if 0.3 <= hav(samp[i], samp[j]) <= 5*lam]
    c_hop = float(np.median(ratios))
    out[r["line"]] = dict(lam=round(lam,3), c_hop=round(c_hop,3), npair=len(ratios))
    V, K, A = r["V"], r["K"], r["A_hull"]
    p_prior = r["meas_osrm"] / (1.22*(BETA*math.sqrt(V*A) + KAPPA*math.sqrt(K*A)))
    p_hop = r["meas_osrm"] / (c_hop*(BETA*math.sqrt(V*A) + KAPPA*math.sqrt(K*A)))
    rs_prior.append(p_prior); rs_hop.append(p_hop)
    print(f"{r['line']:<11}{A/r['n']:>6.2f}{lam:>6.2f}{1.22:>8.2f}{c_hop:>7.3f}"
          f"{p_prior:>12.3f}{p_hop:>11.3f}", flush=True)

json.dump(out, open("/tmp/output/beijing_chop.json", "w"), indent=1)
for name, rs in [("two/c_prior", rs_prior), ("two/c_hop", rs_hop)]:
    cov = sum(1 for x in rs if 0.75 <= x <= 1.30)
    print(f"{name}: median={np.median(rs):.3f} cov={cov}/{len(rs)}")
# 密度分层 in c_hop
dens = [r["A_hull"]/r["n"] for r in rows]
lo_d = [x for dd, x in zip(dens, rs_hop) if dd < 0.5]
hi_d = [x for dd, x in zip(dens, rs_hop) if dd >= 0.5]
print(f"c_hop 分层: A/n<0.5 median={np.median(lo_d):.3f} cov={sum(1 for x in lo_d if 0.75<=x<=1.3)}/{len(lo_d)}; "
      f"A/n>=0.5 median={np.median(hi_d):.3f} cov={sum(1 for x in hi_d if 0.75<=x<=1.3)}/{len(hi_d)}")
