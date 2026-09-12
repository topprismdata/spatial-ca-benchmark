"""Beijing fresh-holdout validation (v0.3.0 release gate, spec §5.2/§5.6).

18 fresh lines from 全部.xlsx (NP9902504 excluded = burned Fangshan).
Measured: OSRM road-network distance along ACTUAL visit sequence (inter-stop,
no depot return), WGS84-converted from GCJ02.
Predictions compared: pure-BHH mid vs two-term mid (beta*sqrt(VA)+kappa*sqrt(KA)).
c = 1.22 Beijing urban_plain_grid city_prior. Gates frozen: coverage >= 8/10
per branch on the [0.75,1.30] policy band (median in [0.90,1.30]).
"""
import json, math, subprocess, time, sys
import numpy as np
import pandas as pd
from scipy.spatial import ConvexHull

BETA, KAPPA, C_BJ = 0.7124, 0.9531, 1.22

# ---- GCJ02 -> WGS84 (standard iterative inverse)
_A = 6378245.0; _EE = 0.00669342162296594
def _t_lat(x, y):
    r = -100 + 2*x + 3*y + 0.2*y*y + 0.1*x*y + 0.2*math.sqrt(abs(x))
    r += (20*math.sin(6*x*math.pi) + 20*math.sin(2*x*math.pi)) * 2/3
    r += (20*math.sin(y*math.pi) + 40*math.sin(y/3*math.pi)) * 2/3
    r += (160*math.sin(y/12*math.pi) + 320*math.sin(y*math.pi/30)) * 2/3
    return r
def _t_lng(x, y):
    r = 300 + x + 2*y + 0.1*x*x + 0.1*x*y + 0.1*math.sqrt(abs(x))
    r += (20*math.sin(6*x*math.pi) + 20*math.sin(2*x*math.pi)) * 2/3
    r += (20*math.sin(x*math.pi) + 40*math.sin(x/3*math.pi)) * 2/3
    r += (150*math.sin(x/12*math.pi) + 300*math.sin(x/30*math.pi)) * 2/3
    return r
def gcj2wgs(lng, lat):
    wlng, wlat = lng, lat
    for _ in range(5):
        glng, glat = wgs2gcj(wlng, wlat)
        wlng += lng - glng; wlat += lat - glat
    return wlng, wlat
def wgs2gcj(wlng, wlat):
    dlat = _t_lat(wlng-105, wlat-35); dlng = _t_lng(wlng-105, wlat-35)
    rl = math.radians(wlat); magic = 1 - _EE*math.sin(rl)**2
    sm = math.sqrt(magic)
    dlat = (dlat*180)/((_A*(1-_EE))/(magic*sm)*math.pi)
    dlng = (dlng*180)/(_A/sm*math.cos(rl)*math.pi)
    return wlng+dlng, wlat+dlat

def curl_json(url, tries=3):
    for k in range(tries):
        try:
            o = subprocess.run(["curl", "-s", "--max-time", "40", url],
                               capture_output=True, text=True, timeout=45)
            return json.loads(o.stdout)
        except Exception:
            time.sleep(1.5 * (k + 1))
    return None

def nn_2opt(coords):
    n = len(coords)
    if n < 4:
        if n == 2: return 2*math.dist(coords[0], coords[1])
        return sum(math.dist(coords[i], coords[(i+1) % n]) for i in range(n))
    arr = np.array(coords)
    D = np.linalg.norm(arr[:, None] - arr[None, :], axis=-1)
    unv = set(range(1, n)); tour = [0]
    while unv:
        last = tour[-1]
        tour.append(min(unv, key=lambda j: D[last, j])); unv.remove(tour[-1])
    def L(t): return sum(D[t[i], t[(i+1) % n]] for i in range(n))
    best = tour[:]; bl = L(best); improved = True
    while improved:
        improved = False
        for i in range(1, n-1):
            for j in range(i+1, n):
                nt = best[:i+1] + best[i+1:j+1][::-1] + best[j+1:]
                nl = L(nt)
                if nl < bl - 1e-9:
                    best, bl, improved = nt, nl, True
    return bl

def osrm_table(coords):
    pts = ";".join(f"{c[0]},{c[1]}" for c in coords)
    d = curl_json(f"https://router.project-osrm.org/table/v1/driving/{pts}?annotations=distance")
    if d and d.get("code") == "Ok":
        return np.array(d["distances"]) / 1000.0
    return None

def main():
    df = pd.read_excel("/Users/ghb/Downloads/全部.xlsx")
    df["客户编码"] = df["客户编码"].astype(str)
    bj = df[df["province"].astype(str).str.strip() == "110000"].copy()
    lines = [l for l in bj["销售编码"].unique() if l != "NP9902504"]
    print(f"fresh lines: {len(lines)}")

    rows = []
    for li, line in enumerate(lines):
        ln = bj[bj["销售编码"] == line]
        # 店坐标 (GCJ02 -> WGS84 + 保留 GCJ02 给框架)
        sd = ln.groupby("客户编码")[["lng", "lat"]].first()
        pts_g = list(zip(sd["lng"], sd["lat"]))
        pts_w = [gcj2wgs(a, b) for a, b in pts_g]
        code2i = {c: i for i, c in enumerate(sd.index)}
        n = len(pts_g); V = len(ln); f = V / n
        K = pd.to_datetime(ln["拜访日期"]).dt.normalize().nunique()  # 实际出车天数=日行程数

        lat0 = np.mean([p[1] for p in pts_w])
        kx, ky = 111.32 * math.cos(math.radians(lat0)), 110.574
        xy = np.array([(p[0]*kx, p[1]*ky) for p in pts_w])
        a_hull = ConvexHull(xy).volume

        # 实测: 实际拜访序 OSRM 距离 (逐服务日, inter-stop)
        meas_osrm = 0.0; ok = True
        for dte, day in ln.groupby(pd.to_datetime(ln["拜访日期"]).dt.normalize()):
            day = day.sort_values("拜访顺序")
            idx = [code2i[c] for c in day["客户编码"]]
            seq = [pts_w[i] for i in idx]
            wp = ";".join(f"{c[0]},{c[1]}" for c in seq)
            d = curl_json(f"https://router.project-osrm.org/route/v1/driving/{wp}?overview=false")
            if d and d.get("code") == "Ok" and d.get("routes"):
                meas_osrm += d["routes"][0]["distance"] / 1000.0
            else:
                ok = False
        # TSP 重排口径 (片区最优): OSRM table + 2opt
        tsp_osrm = 0.0
        for dte, day in ln.groupby(pd.to_datetime(ln["拜访日期"]).dt.normalize()):
            idx = [code2i[c] for c in day["客户编码"]]
            sub = [pts_w[i] for i in idx]
            if len(sub) < 3: continue
            if len(sub) <= 95:
                tm = osrm_table(sub)
            else:
                tm = None
            if tm is not None:
                # 2opt on OSRM matrix (tour, closed chain over day's set)
                nn = len(sub); arr = tm
                unv = set(range(1, nn)); tour = [0]
                while unv:
                    last = tour[-1]
                    tour.append(min(unv, key=lambda j: arr[last, j])); unv.remove(tour[-1])
                def L(t): return sum(arr[t[i], t[(i+1) % nn]] for i in range(nn))
                best = tour[:]; bl = L(best); improved = True; itc = 0
                while improved and itc < 50:
                    improved = False; itc += 1
                    for i in range(1, nn-1):
                        for j in range(i+1, nn):
                            nt = best[:i+1] + best[i+1:j+1][::-1] + best[j+1:]
                            nl = L(nt)
                            if nl < bl - 1e-9:
                                best, bl, improved = nt, nl, True
                tsp_osrm += bl
            else:
                tsp_osrm += nn_2opt(sub) * C_BJ  # 兜底: 欧氏×c

        mid_pure = BETA * C_BJ * math.sqrt(V * a_hull)
        mid_two = C_BJ * (BETA * math.sqrt(V * a_hull) + KAPPA * math.sqrt(K * a_hull))
        rows.append(dict(line=line, n=n, V=V, f=round(f,2), K=int(K),
                         A_hull=round(a_hull,1),
                         meas_osrm=round(meas_osrm,1), tsp_osrm=round(tsp_osrm,1),
                         mid_pure=round(mid_pure,1), mid_two=round(mid_two,1),
                         r_pure_meas=round(meas_osrm/mid_pure,3),
                         r_two_meas=round(meas_osrm/mid_two,3),
                         r_pure_tsp=round(tsp_osrm/mid_pure,3),
                         r_two_tsp=round(tsp_osrm/mid_two,3),
                         complete=ok))
        r = rows[-1]
        print(f"[{li+1:>2}] {line:<10} n={n:>4} f={r['f']:>4} K={r['K']} "
              f"A={r['A_hull']:>7.1f} meas={r['meas_osrm']:>8.1f} mid2={r['mid_two']:>8.1f} "
              f"r_pure={r['r_pure_meas']:.3f} r_two={r['r_two_meas']:.3f} "
              f"tsp_r_pure={r['r_pure_tsp']:.3f} tsp_r_two={r['r_two_tsp']:.3f}", flush=True)

    json.dump(rows, open("output/beijing_holdout_v1.json", "w"), indent=1)
    comp = [r for r in rows if r["complete"]]
    for tag in ("pure", "two"):
        for meas in ("meas", "tsp"):
            rs = [r[f"r_{tag}_{meas}"] for r in comp]
            cov = sum(1 for x in rs if 0.75 <= x <= 1.30)
            print(f"{tag:>4}/{meas:<4}: median={np.median(rs):.3f} cov[0.75,1.3]={cov}/{len(rs)}")

if __name__ == "__main__":
    main()
