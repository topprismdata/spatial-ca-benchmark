# tests/test_report.py
import json
import random
import unittest
from spatial_ca.band import classify
from spatial_ca.report import (BLOCKED_BY_DATA_QUALITY,
                               INCLUDING_CONFIRMED_OUTLIER, PASSED,
                               PASSED_WITH_INVALID_ROWS_DROPPED,
                               STRUCTURE_ONLY, preassess)


def cloud(n=201, seed=1):
    rnd = random.Random(seed)
    return [(115.9 + rnd.random() * 0.3, 39.55 + rnd.random() * 0.2)
            for _ in range(n)]


class TestPreassess(unittest.TestCase):
    def test_source_crs_required(self):
        with self.assertRaises(TypeError):
            preassess(cloud(), total_visits=242, available_workdays=21)

    def test_all_invalid_raises(self):
        with self.assertRaises(ValueError):
            preassess([(0.0, 0.0)], total_visits=1, available_workdays=1,
                      source_crs="WGS84")

    def test_unadjudicated_outlier_blocks_band(self):
        rep = preassess(cloud() + [(118.9, 41.6)], total_visits=242,
                        available_workdays=21, source_crs="WGS84")
        self.assertEqual(rep.gate, BLOCKED_BY_DATA_QUALITY)
        self.assertIsNone(rep.band)
        self.assertEqual(rep.assessment["status"],
                         "NOT_ASSESSED_DATA_QUALITY_BLOCKED")
        self.assertEqual([s["original_index"]
                          for s in rep.structural["suspects"]], [201])

    def test_confirm_drop_unblocks_with_lineage(self):
        rep = preassess(cloud() + [(118.9, 41.6)], total_visits=242,
                        available_workdays=21, source_crs="WGS84",
                        confirm_drop=(201,))
        self.assertEqual(rep.gate, PASSED)
        self.assertEqual(rep.lineage["dropped_by_user"], [201])
        self.assertIsNotNone(rep.band)

    def test_invalid_rows_earn_their_own_gate(self):
        rep = preassess(cloud() + [(110.0, 110.0)], total_visits=242,
                        available_workdays=21, source_crs="WGS84")
        self.assertEqual(rep.gate, PASSED_WITH_INVALID_ROWS_DROPPED)
        self.assertEqual(rep.lineage["dropped_invalid"], [201])

    def test_confirm_keep_marks_lineage_and_band(self):
        rep = preassess(cloud() + [(118.9, 41.6)], total_visits=242,
                        available_workdays=21, source_crs="WGS84",
                        confirm_keep=(201,))
        self.assertEqual(rep.gate, INCLUDING_CONFIRMED_OUTLIER)
        self.assertEqual(rep.lineage["kept_confirmed_outlier"], [201])
        self.assertTrue(rep.band["including_confirmed_outlier"])

    def test_unknown_crs_blocks_absolute_km(self):
        rep = preassess(cloud(), total_visits=242, available_workdays=21,
                        source_crs="UNKNOWN", measured_km=536.3)
        self.assertEqual(rep.gate, STRUCTURE_ONLY)
        self.assertIsNone(rep.band)
        self.assertEqual(rep.assessment["status"],
                         "NOT_ASSESSED_CRS_UNCONFIRMED")
        self.assertTrue(rep.structural["frame_relative"])

    def test_reference_only_without_measured(self):
        rep = preassess(cloud(), total_visits=242, available_workdays=21,
                        source_crs="WGS84")
        self.assertEqual(rep.assessment["status"], "REFERENCE_ONLY")

    def test_measured_classification_matches_band(self):
        rep = preassess(cloud(), total_visits=242, available_workdays=21,
                        source_crs="WGS84", measured_km=536.3)
        self.assertEqual(
            rep.assessment["status"],
            classify(rep.assessment["measured_total_km"], rep.band))

    def test_measured_scope_caveat(self):
        rep = preassess(cloud(), total_visits=242, available_workdays=21,
                        source_crs="WGS84", measured_km=600.0,
                        measured_scope="with_stem_round_trip")
        self.assertIn("scope_caveat", rep.assessment)

    def test_k_semantics_exposed(self):
        rep = preassess(cloud(), total_visits=242, available_workdays=21,
                        source_crs="WGS84")
        self.assertEqual(rep.k["available_workdays"], 21)
        self.assertIsNone(rep.k["active_visit_days"])

    def test_json_serialisable(self):
        rep = preassess(cloud(), total_visits=242, available_workdays=21,
                        source_crs="WGS84", city="天津市")
        json.dumps(rep.to_dict())


if __name__ == "__main__":
    unittest.main()
