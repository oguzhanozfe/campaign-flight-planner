import json
from pathlib import Path
import unittest

from pipeline import prepare, export


def fixture():
    return json.loads(
        Path(__file__).with_name("example.json").read_text(encoding="utf-8")
    )


class PipelineTests(unittest.TestCase):
    def test_contiguous_window_and_audience(self):
        d = fixture()
        r = prepare(d)
        slots = {x["flight"]: x for x in r["candidates"]}
        self.assertEqual(slots["Proof cut"]["start"], "2026-10-07")
        self.assertEqual(slots["Founder cut"]["start"], "2026-10-05")
        self.assertNotIn("Pack trial", slots)

    def test_existing_conflicts_not_silently_removed(self):
        d = fixture()
        d["booked"].append(dict(d["booked"][0], id="Extra"))
        r = prepare(d)
        self.assertEqual(r["metrics"]["Existing conflicts"], 4)
        self.assertEqual(
            export(d, r, [])["creative-flights.ics"].count("BEGIN:VEVENT"), 2
        )

    def test_selected_ics_and_utf8_folding(self):
        d = fixture()
        d["flights"][0]["id"] = "Café " * 14
        r = prepare(d)
        out = export(d, r, [r["candidates"][0]])["creative-flights.ics"]
        self.assertIn("DTEND;VALUE=DATE:20261009", out)
        self.assertEqual(out.count("BEGIN:VEVENT"), 2)
        self.assertTrue(all(len(l.encode()) <= 75 for l in out.split("\r\n")))

    def test_window_validation(self):
        d = fixture()
        d["flights"][0]["earliest"] = "2026-02-31"
        with self.assertRaises(ValueError):
            prepare(d)


if __name__ == "__main__":
    unittest.main()
