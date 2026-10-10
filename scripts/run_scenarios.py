"""Run every CP5 scenario in a directory and print the rubric summary.

    python3 scripts/run_scenarios.py <dir> [--json]

Each *.json file in <dir> (sorted by name) is a scenario for
perception.scenario_runner.run_scenario. It runs against a fresh ObjectStore on
a temporary database (deleted afterwards), with the scenario's own identity
declaration (the synthetic tag embedder when it asks for one); no network, no
real model, no real footage. Per scenario one line per query (shape, outcome,
expectation, OK / MISMATCH), then perception.rubric.summarize over every query
record, ending with the no-accuracy-claim sentence. Exit status 1 when any
scenario failed to run or any expected outcome or shape did not match; 2 for a
usage error. --json prints the summary as JSON after the human-readable lines.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from perception.rubric import NO_CLAIM_SENTENCE, summarize  # noqa: E402
from perception.scenario_runner import ScenarioError, run_scenario  # noqa: E402


def make_factory(directory, name):
    """A store_factory for one scenario: ObjectStore on <directory>/<name>.sqlite3."""
    def factory(clock):
        from perception.object_memory import ObjectStore
        return ObjectStore(Path(directory) / f"{name}.sqlite3", profile_id="local", clock=clock)
    return factory


def run_directory(directory, out=sys.stdout):
    """Run every scenario file; returns (records, failed: bool)."""
    paths = sorted(Path(directory).glob("*.json"))
    if not paths:
        print(f"no *.json scenarios in {directory}", file=out)
        return [], True
    records, failed = [], False
    with tempfile.TemporaryDirectory(prefix="pam-cp5-scenarios-") as temp:
        for path in paths:
            print(f"== {path.name}", file=out)
            try:
                results = run_scenario(path, store_factory=make_factory(temp, path.stem))
            except ScenarioError as exc:
                print(f"   ERROR {exc}", file=out)
                failed = True
                continue
            except Exception as exc:  # a store refusal or a bug; the type is enough to locate it
                print(f"   ERROR {type(exc).__name__} while running the scenario", file=out)
                failed = True
                continue
            for record in results:
                expected = record.get("expected") or {}
                want = ", ".join(f"{key}={expected[key]}" for key in ("shape", "outcome") if key in expected) or "no expectation"
                verdict = "OK" if record["ok"] else ("MISMATCH" if record["ok"] is False else "-")
                if record["ok"] is False:
                    failed = True
                print(f"   step {record['step']:>3}  {record['query']!r}: shape={record['answer']['shape']} outcome={record['outcome']}"
                      f"  [{want}]  {verdict}", file=out)
            records.extend(results)
    return records, failed


def main(argv):
    args = [value for value in argv if not value.startswith("--")]
    if len(args) != 1 or not Path(args[0]).is_dir():
        print(__doc__, file=sys.stderr)
        return 2
    # The no-accuracy-claim sentence frames the run: first line and last line.
    print(NO_CLAIM_SENTENCE)
    records, failed = run_directory(args[0])
    summary = summarize(records)
    print("== summary")
    # "queries" is the total asked (the rubric's `asked` key keeps its meaning in the dict).
    print(f"   queries: {summary['asked']}")
    for key in ("answered", "clarified", "abstained", "correct_among_answered", "coverage", "confident_wrong_rate", "hedged_wrong_rate"):
        value = summary[key]
        print(f"   {key}: {round(value, 4) if isinstance(value, float) else value}")
    print(f"   outcomes: {json.dumps(summary['outcomes'], sort_keys=True)}")
    print(f"   medication: {json.dumps(summary['medication'], sort_keys=True)}")
    print(f"   fidelity: {json.dumps(summary['fidelity'], sort_keys=True)}")
    if "--json" in argv:
        print(json.dumps(summary, sort_keys=True))
    print(NO_CLAIM_SENTENCE)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
