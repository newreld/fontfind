import tempfile
import unittest
from pathlib import Path

from fontfind import db, pipeline, status


class PipelineTests(unittest.TestCase):
    def test_find_and_screen_phases_expand(self):
        self.assertEqual(pipeline.expand(["find", "screen", "judge"], False), ["roundups", "searches", "peers", "screen", "promote", "judge"])

    def test_deep_adds_sources_first(self):
        self.assertEqual(pipeline.expand(["judge"], True), ["sources", "judge"])

    def test_default_steps(self):
        self.assertEqual(pipeline.expand(None, False), pipeline.STEPS)

    def test_overall_progress(self):
        st = status.Status(["a", "b"])
        st.start("a"); st.plan(4); st.tick("x", 2)
        self.assertAlmostEqual(st.overall(), 0.25)
        st.start("b")
        self.assertAlmostEqual(st.overall(), 0.5)

    def test_save_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "f.yaml"
            db.save([{"name": "X", "website": "https://x.test"}], path)
            self.assertEqual([p.name for p in Path(d).iterdir()], ["f.yaml"])


if __name__ == "__main__":
    unittest.main()


class PhaseTests(unittest.TestCase):
    def test_find_and_evaluate_cover_all_steps(self):
        both = pipeline.expand(["find", "screen", "review"], False)
        self.assertEqual(both, pipeline.STEPS)
        self.assertFalse(set(pipeline.PHASES["find"]) & set(pipeline.PHASES["review"]))
