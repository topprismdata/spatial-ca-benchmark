# tests/test_band.py
import math
import random
import unittest
from spatial_ca.band import BETA, ENVELOPE_VERSION, KAPPA_BOUNDARY, ca_band, classify
from spatial_ca.geometry import clean_coordinates


def cloud(n=201, seed=20260911):
    rnd = random.Random(seed)
    return [(115.9 + rnd.random() * 0.3, 39.55 + rnd.random() * 0.2)
            for _ in range(n)]


def cr():
    return clean_coordinates(cloud(), source_crs="WGS84")


class TestBand(unittest.TestCase):
    def test_single_beta(self):
        self.assertAlmostEqual(BETA, 0.7124)

    def test_mid_formula_exact(self):
        # v0.3.0 two-term model: interior BHH + boundary perimeter term
        b = ca_band(cr(), total_visits=242, available_workdays=21)
        A = b["geometry"]["hull_area_km2"]
        expected = b["circuity"]["value"] * (
            BETA * math.sqrt(242 * A)
            + KAPPA_BOUNDARY * math.sqrt(21 * A))
        # A/mid 各自 round(2): 反推伪差 < 0.015 km 级
        self.assertAlmostEqual(b["reference_mid_km"], expected, delta=0.05)

    def test_rigid_shift_invariance_theorem(self):
        base = ca_band(cr(), 242, 21)
        shifted_pts = [(x + 0.0062, y) for x, y in cloud()]
        shift = ca_band(clean_coordinates(shifted_pts, source_crs="WGS84"),
                        242, 21)
        self.assertAlmostEqual(base["reference_mid_km"],
                               shift["reference_mid_km"], delta=0.05)
        # 定理内容 = 严格相等; 容差只吸收输出的 round(2) 伪差。
        # 本测试同时是 C1.2 的可执行声明: 平移前后一切内部量相同,
        # 因此整批 CRS 错配在原理上不可能被内部几何发现。

    def test_k_dependence_boundary_term(self):
        # v0.3.0: monthly total is NOT K-invariant (synthetic v1 falsified
        # the pure-BHH axiom: districting overhead scales as kappa*sqrt(K*A))
        b21 = ca_band(cr(), 242, 21)
        b23 = ca_band(cr(), 242, 23)
        self.assertGreater(b23["reference_mid_km"], b21["reference_mid_km"])
        # K 增量必须精确等于边界项解析差 c·κ·√A·(√23-√21)
        A = b21["geometry"]["hull_area_km2"]
        c = b21["circuity"]["value"]
        expected_delta = c * KAPPA_BOUNDARY * math.sqrt(A) * (
            math.sqrt(23) - math.sqrt(21))
        self.assertAlmostEqual(
            b23["reference_mid_km"] - b21["reference_mid_km"],
            expected_delta, delta=0.05)
        # 日里程 = T/K: K 越大, 日带越低 (V2 曾写反, 评审修正)
        self.assertGreater(b21["daily"]["band_km"][1],
                           b23["daily"]["band_km"][1])

    def test_policy_envelope_explicit(self):
        b = ca_band(cr(), 242, 21, city="天津市")
        self.assertEqual(b["band_method"],
                         f"heuristic_policy_envelope_{ENVELOPE_VERSION}")
        self.assertEqual(b["statistical_confidence_interval"], False)
        lo, hi = b["reference_band_km"]
        mid = b["reference_mid_km"]
        self.assertAlmostEqual(lo, mid * 0.75, delta=0.02)
        self.assertAlmostEqual(hi, mid * 1.30, delta=0.02)
        self.assertEqual(b["envelope_multipliers"], [0.75, 1.3])

    def test_beta_fields_separated(self):
        b = ca_band(cr(), 242, 21)
        self.assertEqual(b["beta"]["point_estimate"], 0.7124)
        self.assertEqual(b["beta"]["published_mathematical_bounds"],
                         [0.6277, 0.9038])
        self.assertFalse(b["beta"]["bounds_used_in_operational_band"])

    def test_user_override_narrows_envelope(self):
        b = ca_band(cr(), 242, 21, circuity_override=1.4)
        self.assertEqual(b["circuity"]["source"], "user_override")
        lo, hi = b["reference_band_km"]
        mid = b["reference_mid_km"]
        self.assertAlmostEqual(lo, mid * 0.88, delta=0.02)
        self.assertAlmostEqual(hi, mid * 1.12, delta=0.02)

    def test_thin_daily_widens_and_announces(self):
        small = clean_coordinates(cloud(n=40), source_crs="WGS84")
        b = ca_band(small, 40, 20)          # 日均 2 店 < 4
        self.assertTrue(b["small_sample_warning"])
        lo, hi = b["reference_band_km"]
        mid = b["reference_mid_km"]
        self.assertLess(lo, mid * 0.72)    # city_prior 0.75 -> 0.68
        self.assertGreater(hi, mid * 1.40)  # 1.30 -> 1.45

    def test_closed_tour_widens_hi(self):
        o = ca_band(cr(), 242, 21, city="天津市")
        c = ca_band(cr(), 242, 21, city="天津市", is_closed_tour=True)
        self.assertEqual(o["reference_mid_km"], c["reference_mid_km"])
        self.assertGreater(c["reference_band_km"][1],
                           o["reference_band_km"][1])

    def test_unknown_crs_band_blocked(self):
        from spatial_ca.geometry import UNKNOWN
        raw = clean_coordinates(cloud(), source_crs=UNKNOWN)
        with self.assertRaises(ValueError):
            ca_band(raw, 242, 21)

    def test_degenerate_flag_not_swallowed(self):
        line = clean_coordinates([(116.0, 39.0), (116.01, 39.0),
                                  (116.02, 39.0), (116.03, 39.0)],
                                 source_crs="WGS84")
        b = ca_band(line, 8, 4)
        self.assertTrue(b["degenerate_geometry"])

    def test_degenerate_diagonal_collinear(self):
        # equirectangular float noise makes diagonal collinear area ~1e-5:
        # must still be flagged (ratio guard, not area<=0)
        diag = [(117.0 + i * 0.1, 39.0 + i * 0.1) for i in range(4)]
        b = ca_band(clean_coordinates(diag, source_crs="WGS84"), 8, 4)
        self.assertTrue(b["degenerate_geometry"])

    def test_thin_valley_is_not_degenerate(self):
        import random
        rnd = random.Random(9)
        valley = [(116.0 + (i / 199) * 0.5,
                   39.0 + rnd.uniform(-0.002, 0.002)) for i in range(200)]
        b = ca_band(clean_coordinates(valley, source_crs="WGS84"), 200, 20)
        self.assertFalse(b["degenerate_geometry"])

    def test_regime_fields(self):
        # sparse: V/N = 242/201 = 1.2 -> sparse_partitioned
        b = ca_band(cr(), 242, 21)
        self.assertEqual(b["regime"], "sparse_partitioned")
        # dense: V/N = 800/201 = 3.98 -> dense_revisit (band value itself is
        # known-wrong there; report layer refuses it, band only labels it)
        b2 = ca_band(cr(), 800, 21)
        self.assertEqual(b2["regime"], "dense_revisit")
        self.assertAlmostEqual(b2["visits_per_store"], 3.98, places=2)

    def test_classify_consistency(self):
        b = ca_band(cr(), 242, 21)
        mid = b["reference_mid_km"]
        hi = b["reference_band_km"][1]
        self.assertEqual(classify(0.5 * mid, b), "BELOW_CA_REFERENCE")
        self.assertEqual(classify(mid, b), "CONSISTENT_WITH_CA_REFERENCE")
        self.assertEqual(classify(1.2 * hi, b), "ABOVE_CA_REFERENCE")
        self.assertEqual(classify(3.0 * hi, b),
                         "STRONGLY_INCONSISTENT_WITH_CA")


if __name__ == "__main__":
    unittest.main()
