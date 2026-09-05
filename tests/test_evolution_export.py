import json
import tempfile
import unittest
from pathlib import Path

from analysis.build_analytics import write_json
from analysis.builders.evolution import content_evolution_payload, export_evolution_shards


class EvolutionExportTest(unittest.TestCase):
    def test_updates_counts_when_index_ranking_eligibility_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "dynamic-content-hotspots-2024.json"
            row = ["2024-01", "GPT-4", 30, 2, 2, 1, 0, 2, 0, 0, 0, False]
            write_json(source, {"rows": [row]})
            index_path = root / "dynamic-content-hotspots-index.json"
            write_json(index_path, {
                "year_shards": {"2024": source.name},
                "terms": {"GPT-4": {"ranked": False}},
            })
            export_evolution_shards(root, write_json)
            index = json.loads(index_path.read_text())
            output = root / index["evolution_shards"]["2024"]
            self.assertEqual(json.loads(output.read_text())["counts"], [])
            source_mtime = source.stat().st_mtime_ns
            index["terms"]["GPT-4"]["ranked"] = True
            write_json(index_path, index)
            export_evolution_shards(root, write_json)
            self.assertEqual(json.loads(output.read_text())["counts"], [row[:3]])
            self.assertEqual(source.stat().st_mtime_ns, source_mtime)

    def test_preserves_counts_outside_top_thirty_without_hidden_family_members(self):
        rows = [
            ["2024-01", term, count, 2, 2, 1, 0, 2, 0, rank, 0, False]
            for term, count, rank in (("AI", 100, 1), ("GLM", 20, 31), ("GPT-4", 30, 0))
        ]
        payload = {"rows": rows, "annual_rows": [["2024", *row[1:]] for row in rows]}
        result = content_evolution_payload(payload, {"GPT-4": {"ranked": False}})
        self.assertEqual(result["counts"], [row[:3] for row in rows[:2]])
        self.assertEqual(result["rows"], rows[:1])
        self.assertEqual(result["annual_rows"], [["2024", *rows[0][1:]]])

    def test_exports_and_reuses_unchanged_shards_and_removes_stale_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "dynamic-topic-rows-2024.json"
            write_json(source, {
                "rows": [["2024-01", "AI", 10, 20, 100]],
                "group_topic_rows": [["2024-01", "ai", "AI", 10]],
            })
            write_json(root / "dynamic-topics.json", {"row_shards": {"2024": source.name}})
            stale = root / "dynamic-topic-evolution-1999.json"
            write_json(stale, {})
            export_evolution_shards(root, write_json)
            index = json.loads((root / "dynamic-topics.json").read_text())
            self.assertFalse(stale.exists())
            output = root / index["evolution_shards"]["2024"]
            self.assertEqual(json.loads(output.read_text())["rows"], [["2024-01", "AI", 10, 20]])
            self.assertEqual(json.loads((root / index["group_shards"]["2024"]).read_text())["group_topic_rows"], [["2024-01", "ai", "AI", 10]])
            before = output.stat().st_mtime_ns
            export_evolution_shards(root, write_json)
            self.assertEqual(output.stat().st_mtime_ns, before)
            write_json(source, {"rows": [["2024-01", "AI", 11, 22, 100]]})
            export_evolution_shards(root, write_json)
            self.assertEqual(json.loads(output.read_text())["rows"][0][2], 11)


if __name__ == "__main__":
    unittest.main()
