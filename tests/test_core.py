from __future__ import annotations

import sqlite3
import unittest

from radar.archive import rebuild_archive_matches
from radar.briefs import generate_brief, generate_keywords
from radar.clustering import rebuild_clusters
from radar.db import init_db, rows
from radar.demo_seed import seed_demo
from radar.nlp import extract_entities, infer_desk, tokenize
from radar.scoring import confidence_label, freshness_score, opportunity_score, source_score


class EditorialRadarCoreTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        seed_demo(self.conn)

    def test_nlp_desk_inference(self):
        self.assertEqual(infer_desk("NEET counselling NTA exam result"), "Education")
        self.assertEqual(infer_desk("Iran Israel conflict global leaders"), "World")
        self.assertGreater(len(tokenize("Delhi rain alert IMD update")), 1)
        self.assertIn("NEET", extract_entities("NEET Counselling Update By NTA"))

    def test_scoring_bounds(self):
        self.assertGreaterEqual(freshness_score(None), 0)
        self.assertLessEqual(freshness_score(None), 100)
        self.assertGreater(source_score(["official", "trusted"]), source_score(["low"]))
        score = opportunity_score(80, 70, 60, 50)
        self.assertGreater(score, 0)
        self.assertIn(confidence_label(4, 3, 70, 80), {"Verified", "Likely"})

    def test_cluster_and_archive_build(self):
        cluster_count = rebuild_clusters(self.conn)
        self.assertGreater(cluster_count, 0)
        match_count = rebuild_archive_matches(self.conn)
        self.assertGreater(match_count, 0)
        clusters = rows(self.conn, "SELECT * FROM topic_clusters ORDER BY opportunity_score DESC")
        self.assertGreater(len(clusters), 0)
        self.assertTrue(any(float(c["archive_score"]) > 0 for c in clusters))

    def test_generate_brief_and_keywords(self):
        rebuild_clusters(self.conn)
        rebuild_archive_matches(self.conn)
        cluster = rows(self.conn, "SELECT id FROM topic_clusters ORDER BY opportunity_score DESC LIMIT 1")[0]
        brief = generate_brief(self.conn, cluster["id"])
        self.assertIn("Editorial Brief", brief)
        self.assertIn("Evidence", brief)
        pack = generate_keywords("NEET Counselling Update", "YouTube")
        self.assertTrue(pack["primary"])
        self.assertTrue(pack["secondary"])


if __name__ == "__main__":
    unittest.main()
