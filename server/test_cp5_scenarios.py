"""CP5 acceptance: the scripted scenarios through the scenario runner.

    python3 -B server/test_cp5_scenarios.py -v

Authority: docs/BUILD_PLAN.md "CP5 in detail", *Scenario runner (A, scenarios by the
Tester)*: perception.scenario_runner.run_scenario(path, *, store_factory) -> list[record]
executes a JSON scenario (server/fixtures/cp5/scenarios/*.json; the schema is the
runner's docstring, summarised in the README there) against a real store, scoring every
query with perception.rubric; scripts/run_scenarios.py runs a directory and prints the
rubric summary with the no-accuracy-claim sentence. Every scenario here runs with a
store_factory built from the fixtures (a temporary database per run, the build's consent
acknowledged, the runner's own synthetic tag embedder and an approved wide calibration
when the scenario names them); every query's rubric outcome and answer shape must match
the scenario's expectation (and the record's own "ok"); the summary carries
NO_CLAIM_SENTENCE and never reads as an accuracy claim; the script runs the directory
with exit 0 and fails on a wrong expectation.

Expected outcomes are software-correctness expectations on synthetic data, never
accuracy claims.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_memory_bootstrap as bootstrap  # noqa: E402
import test_cp5_fixtures as cp5  # noqa: E402
from test_cp5_fixtures import check_answer, find_value, load_scenarios, query_medication, scenario_queries  # noqa: E402

ACCURACY_CLAIM = re.compile(r"accuracy of (the )?(system|pam|model|answers?|resolver)|is \d+% accurate|measured accuracy", re.IGNORECASE)
SCRIPT = ROOT / "scripts" / "run_scenarios.py"
RECORD_KEYS = {"step", "kind", "clock_ms", "query", "answer", "truth", "outcome", "fidelity", "expected", "ok", "coverage"}


def query_records(records):
    return [r for r in records if isinstance(r, dict) and r.get("kind", "query") == "query" and isinstance(r.get("answer"), dict)]


class ScenarioFixture(unittest.TestCase):
    """A fresh temporary directory per test; the store factory the runner gets."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pam-cp5-scenarios-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.serial = 0
        self.stores = []

    def store_factory(self, clock=None, *args, **kwargs):
        """store_factory(clock) -> store: a new ObjectStore on a temporary database
        around the runner's clock, the build's consent acknowledged (the runner does
        so too; idempotent). The embedder and calibration come from the scenario's
        own identity block, which the runner applies to this store."""
        from perception.object_memory import ObjectStore
        self.serial += 1
        path = self.root / f"scenario-{self.serial}.sqlite3"
        store = ObjectStore(path, profile_id="local", clock=clock) if callable(clock) else ObjectStore(path, profile_id="local")
        store.acknowledge_consent(bootstrap.CONSENT_VERSION, "test")
        self.stores.append(store)
        return store

    def run_scenario(self, scenario):
        from perception.scenario_runner import run_scenario
        records = run_scenario(scenario["_path"], store_factory=self.store_factory)
        self.assertIsInstance(records, list, records)
        return records

    def summarize(self, records):
        from perception import rubric
        return rubric.summarize(records)


class ScenarioRunTests(ScenarioFixture):
    def check_scenario_run(self, scenario):
        records = self.run_scenario(scenario)
        expected = scenario_queries(scenario)
        answered = query_records(records)
        self.assertEqual(len(answered), len(expected), f"one record per query step: {[sorted(r) for r in records][:12]}")
        from perception import rubric
        for index, (step, record) in enumerate(zip(expected, answered)):
            with self.subTest(query=index, text=step["text"]):
                self.assertTrue(RECORD_KEYS <= set(record), sorted(RECORD_KEYS - set(record)))
                self.assertEqual(record["query"], step["text"])
                answer = check_answer(self, record["answer"])
                self.assertEqual(answer["shape"], step["expect"]["shape"], f"shape for {step['text']!r}: {answer['text']!r} basis {answer['basis']}")
                self.assertEqual(record["outcome"], step["expect"]["outcome"], f"outcome for {step['text']!r}: {answer['shape']} {answer['text']!r}")
                self.assertIs(record["ok"], True, f"the runner's own check for {step['text']!r}: expected {record['expected']}, got {answer['shape']} / {record['outcome']}")
                if "expected_index_pending" in step:
                    self.assertIs(answer["index_pending"], step["expected_index_pending"])
                for token in step.get("expected_basis", ()):
                    self.assertIn(token, answer["basis"], f"basis for {step['text']!r}")
                if "expected_gap_ms" in step:
                    self.assertEqual(record["coverage"]["gap_ms"], step["expected_gap_ms"], "coverage loss is reported, never hidden")
                if answer["index_pending"]:
                    for phrase in cp5.PENDING_DENIALS:
                        self.assertNotIn(phrase, answer["text"].lower())
                truth = record["truth"]
                self.assertEqual(set(truth), cp5.TRUTH_KEYS, "the record keeps the rubric truth it was scored against")
                self.assertEqual(truth["medication"], query_medication(scenario, step))
                if step["truth"]["item"] is not None and answer["members"] and step["expect"]["outcome"] in ("correct", "hedged-correct"):
                    self.assertEqual(truth["item_id"], answer["members"][0]["item_id"], "the handle resolved to the answered item's id")
                self.assertEqual(rubric.score(answer, truth), record["outcome"], "the record's outcome is the rubric's")
                self.assertIsInstance(record["fidelity"], (bool, str))
                self.assertTrue(cp5.COVERAGE_KEYS <= set(record["coverage"]), record["coverage"])
        summary = self.summarize(records)
        rendered = json.dumps(summary, default=str)
        self.assertIn(rubric.NO_CLAIM_SENTENCE, rendered)
        stripped = rendered.replace(rubric.NO_CLAIM_SENTENCE, "")
        self.assertIsNone(ACCURACY_CLAIM.search(stripped), stripped[:400])
        self.assertNotIn("accuracy", stripped.lower(), "ruling 1")
        return records, summary

    def test_every_scenario_file_runs_and_matches_its_expectations(self):
        scenarios = load_scenarios()
        self.assertTrue(set(cp5.MANDATORY_SCENARIOS) <= set(scenarios))
        for name, scenario in scenarios.items():
            with self.subTest(scenario=name):
                cp5.check_scenario(self, scenario)
                self.check_scenario_run(scenario)

    def test_new_item_is_never_denied_while_pending(self):
        scenario = load_scenarios()["new_item_before_indexing"]
        records, _ = self.check_scenario_run(scenario)
        first, second = (r["answer"] for r in query_records(records))
        self.assertIs(first["index_pending"], True)
        self.assertEqual(first["shape"], "abstain")
        self.assertIn("index_pending", first["basis"])
        self.assertIs(second["index_pending"], False)
        self.assertEqual(second["shape"], "confident")
        self.assertIsNotNone(second["reference_image"])

    def test_medication_set_summary_splits_medication_queries(self):
        scenario = load_scenarios()["medication_set"]
        records, summary = self.check_scenario_run(scenario)
        medication = [r for r in query_records(records) if r["truth"]["medication"]]
        self.assertEqual(len(medication), len(scenario_queries(scenario)))
        rate = find_value(summary, r"confident.?wrong", within=r"medication")
        self.assertIsNotNone(rate, f"the medication split is reported: {json.dumps(summary, default=str)[:600]}")
        self.assertEqual(float(rate), 0.0, "no confident-wrong on the synthetic medication set")
        coverage = find_value(summary, r"^coverage", within=r"medication")
        self.assertIsNotNone(coverage)
        expected_answered = sum(1 for q in scenario_queries(scenario) if q["expect"]["shape"] in ("confident", "hedged"))
        self.assertAlmostEqual(float(coverage), expected_answered / len(medication), places=6)
        correct = find_value(summary, r"^correct_among_answered$", within=r"medication")
        self.assertIsNotNone(correct, "the medication block reports correct_among_answered (ruling 1)")
        self.assertAlmostEqual(float(correct), 1.0, places=6, msg="every answered medication query here is correct or hedged-correct")

    def test_unobserved_relocation_reports_the_fidelity_split(self):
        scenario = load_scenarios()["unobserved_relocation_then_sighting"]
        records, summary = self.check_scenario_run(scenario)
        answered = query_records(records)
        # Coordinator ruling 2: after a coverage gap the placement is hedged (coverage_gap),
        # never confident; the truthful old place is hedged-wrong for usefulness, fidelity ok.
        self.assertEqual([r["outcome"] for r in answered], ["hedged-wrong", "hedged-correct", "correct"])
        self.assertEqual([r["answer"]["shape"] for r in answered], ["hedged", "hedged", "confident"])
        self.assertIn("coverage_gap", answered[0]["answer"]["basis"])
        self.assertIn("coverage_gap", answered[1]["answer"]["basis"])
        self.assertNotIn("coverage_gap", answered[2]["answer"]["basis"], "fresh evidence after the gap clears it")
        self.assertTrue(answered[0]["fidelity"] in (True, "ok", "fidelity_ok", "correct"), f"the truthful old photo is faithful: {answered[0]['fidelity']!r}")
        self.assertEqual(float(find_value(summary, r"confident.?wrong")), 0.0, "never a confident stale answer")
        self.assertAlmostEqual(float(find_value(summary, r"hedged.?wrong")), 1 / 3, delta=0.00051)
        fidelity = find_value(summary, r"fidelity")
        self.assertIsNotNone(fidelity, f"the fidelity axis is reported: {json.dumps(summary, default=str)[:600]}")
        self.assertTrue(any(leaf in (1.0, 3) for leaf in cp5.leaf_numbers(fidelity)), f"every answered record here was historically faithful: {fidelity!r}")
        # The old photo really is the placement's: the first answer carries it, the second keeps it as history.
        self.assertIsNotNone(answered[0]["answer"]["reference_image"])
        self.assertEqual(answered[1]["answer"]["reference_image"], answered[0]["answer"]["reference_image"])
        self.assertEqual(answered[1]["answer"]["location_status"], "stale")

    def test_coverage_loss_is_reported_by_the_run(self):
        scenario = load_scenarios()["coverage_loss"]
        records, summary = self.check_scenario_run(scenario)
        record = query_records(records)[-1]
        self.assertEqual(record["coverage"]["gap_ms"], 7 * 60 * 1000, "both gaps are in the day's coverage")
        self.assertGreaterEqual(record["coverage"]["camera_on_ms"], 7 * 60 * 1000 + 60 * 1000)
        self.assertEqual(record["coverage"]["sessions"], 1)
        self.assertGreaterEqual(record["coverage"]["idle_sent"], 1)
        # The store behind the run has the telemetry rows and the same coverage.
        store = self.stores[-1]
        day = cp5.utc_day(record["clock_ms"])
        self.assertEqual({k: store.coverage(day)[k] for k in cp5.COVERAGE_KEYS}, {k: record["coverage"][k] for k in cp5.COVERAGE_KEYS})

    def test_lookalike_scenario_keeps_two_rows_and_dissolves_on_assign(self):
        scenario = load_scenarios()["two_refills_lookalikes"]
        records, _ = self.check_scenario_run(scenario)
        answers = [r["answer"] for r in query_records(records)]
        self.assertEqual([a["shape"] for a in answers], ["clarify", "group", "clarify", "confident"])
        group = answers[1]
        self.assertEqual(len(group["members"]), 2, "one group with both bottles, never one merged row")
        self.assertEqual({m["location_text"] for m in group["members"]}, {"fixture shelf left", "fixture shelf right"}, "both locations preserved")
        self.assertRegex(group["unresolved_observation_id"], r"^[0-9a-f]{64}$")
        self.assertEqual({m["identity_status"] for m in group["members"]}, {"ambiguous"})
        store = self.stores[-1]
        items = store.list_items()
        self.assertEqual(len(items), 2, "two physical bottles stay two rows")
        self.assertEqual({i["identity_status"] for i in items}, {"trusted"}, "the assign dissolved the group")
        self.assertEqual(len(store.list_items(query="synthetic evening bottle")), 1)

    def test_malformed_scenarios_are_refused(self):
        from perception.scenario_runner import run_scenario
        good = {k: v for k, v in load_scenarios()["fast_put_down"].items() if k != "_path"}
        bad_cases = {
            "no basis": {k: v for k, v in good.items() if k != "basis"},
            "unknown kind": dict(good, steps=good["steps"] + [{"kind": "teleport"}]),
            "unknown handle": dict(good, steps=good["steps"] + [{"kind": "query", "text": "where", "truth": {"item": "nobody"}}]),
            "bad expect": dict(good, steps=good["steps"] + [{"kind": "query", "text": "where", "truth": {"item": "cup"}, "expect": {"certainty": 1}}]),
            "two items one tag": dict(good, items={"cup": {"label": "a", "tag": 0}, "mug": {"label": "b", "tag": 0}}),
        }
        for name, scenario in bad_cases.items():
            with self.subTest(case=name), self.assertRaises(ValueError):
                run_scenario(scenario, store_factory=self.store_factory)


class ScriptTests(unittest.TestCase):
    def run_script(self, directory, temp):
        env = {key: value for key, value in os.environ.items() if key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL")}
        env.update(PYTHONPATH="", PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", HOME=temp, TMPDIR=temp, TEMP=temp, TMP=temp, PAM_OBJECT_DB="")
        return subprocess.run([sys.executable, "-B", str(SCRIPT), str(directory)], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=600)

    def test_run_scenarios_script_prints_the_summary_and_exits_zero(self):
        self.assertTrue(SCRIPT.is_file(), f"{SCRIPT} is missing")
        from perception import rubric
        before = {p for p in ROOT.rglob("*.sqlite3")}
        with tempfile.TemporaryDirectory(prefix="pam-cp5-script-") as temp:
            result = self.run_script(cp5.SCENARIOS, temp)
        output = result.stdout + "\n" + result.stderr
        self.assertEqual(result.returncode, 0, output[-4000:])
        self.assertIn(rubric.NO_CLAIM_SENTENCE, result.stdout, output[-4000:])
        for name in load_scenarios():
            self.assertIn(name, result.stdout, f"the script names every scenario it ran: {name}")
        lowered = result.stdout.lower()
        for word in ("coverage", "correct_among_answered", "medication", "confident-wrong"):
            self.assertIn(word, lowered, f"the summary reports {word}")
        stripped = result.stdout.replace(rubric.NO_CLAIM_SENTENCE, "")
        self.assertIsNone(ACCURACY_CLAIM.search(stripped), stripped[-1500:])
        self.assertNotIn("accuracy", stripped.lower(), "ruling 1: the word never appears outside the no-claim sentence")
        self.assertNotIn("Traceback", output)
        after = {p for p in ROOT.rglob("*.sqlite3")}
        self.assertEqual(after - before, set(), "the script leaves no database behind in the checkout")

    def test_run_scenarios_script_fails_on_a_wrong_expectation(self):
        # A copy of one scenario with an impossible expectation must make the script
        # exit nonzero: the expectations are checked, not just printed.
        from perception import rubric
        scenario = load_scenarios()["fast_put_down"]
        broken = json.loads(json.dumps({k: v for k, v in scenario.items() if k != "_path"}))
        for step in broken["steps"]:
            if step["kind"] == "query":
                step["expect"] = {"outcome": "confident-wrong", "shape": "confident"}
        with tempfile.TemporaryDirectory(prefix="pam-cp5-script-broken-") as temp:
            directory = Path(temp) / "scenarios"
            directory.mkdir()
            (directory / "fast_put_down.json").write_text(json.dumps(broken, indent=1), encoding="utf-8")
            result = self.run_script(directory, temp)
        self.assertNotEqual(result.returncode, 0, "a mismatched expectation must fail the run")
        self.assertIn(rubric.NO_CLAIM_SENTENCE, result.stdout + result.stderr, "the sentence is printed even on a failed run")


if __name__ == "__main__":
    unittest.main(verbosity=2)
