# tests/test_sanity.py
import os
import random
import unittest
from spatial_ca.geometry import clean_coordinates
from spatial_ca.sanity import adjudicate, find_suspects


def cloud(n=201, seed=20260911):
    rnd = random.Random(seed)
    return [(115.9 + rnd.random() * 0.3, 39.55 + rnd.random() * 0.2)
            for _ in range(n)]


class TestSuspects(unittest.TestCase):
    def test_outlier_inside_bbox_caught(self):
        pts = cloud() + [(118.9, 41.6)]
        cr = clean_coordinates(pts, source_crs="WGS84")
        s = find_suspects(cr)
        # seed 确定性; 若实现时误报额外点则上调 nn_factor 到 10 (非降级)
        self.assertEqual([x["original_index"] for x in s], [201])
        self.assertEqual(s[0]["reason"], "far_outlier")
        self.assertGreater(s[0]["nn_km"], 50.0)

    def test_clean_cloud_no_suspects(self):
        cr = clean_coordinates(cloud(), source_crs="WGS84")
        self.assertEqual(find_suspects(cr), [])

    def test_nn_distance_is_exact(self):
        # 已知构型: 等边三角形(边~0.87km) + 1 远点(117,40)
        a, b, c = (116.0, 39.0), (116.01, 39.0), (116.005, 39.00866)
        far = (117.0, 40.0)
        cr = clean_coordinates([a, b, c, far, far, far], source_crs="WGS84")
        # 三个 far 互为 NN=0 -> 无人可疑
        self.assertEqual(find_suspects(cr, nn_factor=3.0, min_kept=4), [])
        cr2 = clean_coordinates([a, b, c, far], source_crs="WGS84")
        s2 = find_suspects(cr2, nn_factor=3.0, min_kept=4)
        self.assertEqual([x["original_index"] for x in s2], [3])
        self.assertAlmostEqual(s2[0]["nn_km"], 139.3, delta=1.0)
        # 暴力 NN 的真值锚: far->c, 局部均值纬度系 ~139.3 km;
        # ±2格/部分搜索的网格法给不出这个精度 —— 这正是 0.1.0 用暴力的原因

    def test_invalid_points_are_dropped_not_suspects(self):
        cr = clean_coordinates(cloud() + [(110.0, 110.0)], source_crs="WGS84")
        self.assertEqual([d["reason"] for d in cr.dropped], ["outside_bbox"])
        self.assertEqual(find_suspects(cr), [])


class TestAdjudication(unittest.TestCase):
    def setUp(self):
        self.cr = clean_coordinates(cloud() + [(118.9, 41.6)],
                                    source_crs="WGS84")
        self.susp = find_suspects(self.cr)

    def test_unresolved_blocks(self):
        a = adjudicate(self.cr, self.susp, confirm_drop=(), confirm_keep=())
        self.assertEqual(a["decision"], "BLOCKED_BY_DATA_QUALITY")
        self.assertEqual(a["unresolved"], [201])

    def test_drop_rebuilds_with_index_map(self):
        a = adjudicate(self.cr, self.susp, confirm_drop=(201,),
                       confirm_keep=())
        self.assertEqual(a["decision"], "CLEANED")
        self.assertEqual(len(a["points"]), 201)
        self.assertEqual(a["dropped_by_user"], [201])
        self.assertEqual(a["index_map"][200], 200)

    def test_keep_marks_lineage(self):
        a = adjudicate(self.cr, self.susp, confirm_drop=(),
                       confirm_keep=(201,))
        self.assertEqual(a["decision"], "INCLUDING_CONFIRMED_OUTLIER")
        self.assertEqual(a["kept_confirmed_outlier"], [201])
        self.assertEqual(len(a["points"]), 202)

    def test_unknown_drop_index_blocks(self):
        a = adjudicate(self.cr, self.susp, confirm_drop=(0, 201),
                       confirm_keep=())
        self.assertEqual(a["decision"], "BLOCKED_BY_DATA_QUALITY")
        self.assertEqual(a["error"], "unknown_drop_indices")
        self.assertEqual(a["unresolved"], [0])

    def test_conflicting_adjudication_blocks(self):
        a = adjudicate(self.cr, self.susp, confirm_drop=(201,),
                       confirm_keep=(201,))
        self.assertEqual(a["decision"], "BLOCKED_BY_DATA_QUALITY")
        self.assertEqual(a["error"], "conflicting_adjudication")
        self.assertEqual(a["conflicts"], [201])


class TestThroughput(unittest.TestCase):
    """synthetic throughput benchmark - absolute-scale claims belong to
    the 0.2 provable-grid release, not this one."""

    def test_500_stores_under_5s(self):
        import time
        c = clean_coordinates(cloud(500, seed=3), source_crs="WGS84")
        t0 = time.perf_counter()
        find_suspects(c)
        self.assertLess(time.perf_counter() - t0, 5.0)  # 宽松, 防算法级错写

    @unittest.skipUnless(os.environ.get("SPATIAL_CA_PERF"),
                         "nightly synthetic throughput only")
    def test_national_synthetic_throughput(self):
        import json, time
        t0 = time.perf_counter()
        for s in range(571):
            c = clean_coordinates(cloud(200, seed=1000 + s),
                                  source_crs="WGS84")
            find_suspects(c)
        total = time.perf_counter() - t0
        prev = 0.0
        try:
            with open("tests/perf_baseline.json") as fh:
                prev = json.load(fh).get("national_571x200_s", 0.0)
        except OSError:
            pass
        with open("tests/perf_baseline.json", "w") as fh:
            json.dump({"national_571x200_s": round(total, 2),
                       "mode": "bruteforce_v1", "kind": "synthetic"}, fh)
        if prev:                       # 门槛: 相对上一基线退化 < 2x, 非固定秒数
            self.assertLess(total, 2.0 * prev)


if __name__ == "__main__":
    unittest.main()
