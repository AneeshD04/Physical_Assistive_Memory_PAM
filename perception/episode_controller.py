"""Pure causal reference. Times in milliseconds; no inference from missing hands.

step(state, sample) -> (new_state, actions). JSON-compatible input/output.
State: phase idle|busy|settling, last_ms, busy_since, rest_since, burst_taken.
Sample: t_ms (strictly increasing), busy bool|None, motion bool|None,
        frame_valid bool, gap bool (optional, default false).
Actions: start, select_pre_contact, select_hand_busy, select_carry,
         select_release, select_rest, finish, gap, abort.
A carry selection is the FIRST valid frame after observed busy AND motion;
never the midpoint of a future interval. Missing measurements cannot settle.
"""
from __future__ import annotations

BUSY_MIN_MS = 200
REST_MIN_MS = 600
MAX_EPISODE_MS = 10000


def initial_state() -> dict:
    return {"phase": "idle", "last_ms": None, "busy_since": None,
            "rest_since": None, "burst_taken": False}


def step(state: dict | None, sample: dict) -> tuple[dict, list[str]]:
    state = dict(initial_state() if state is None else state)
    t = sample.get("t_ms")
    if type(t) is not int or not 0 <= t <= 9007199254740991:
        raise ValueError("Invalid controller time")
    if state["last_ms"] is not None and t <= state["last_ms"]:
        raise ValueError("Controller time must increase")
    busy, motion = sample.get("busy"), sample.get("motion")
    if any(value is not None and type(value) is not bool for value in (busy, motion)):
        raise ValueError("Invalid controller measurement")
    valid = sample.get("frame_valid", False)
    gap = sample.get("gap", False)
    if type(valid) is not bool or type(gap) is not bool:
        raise ValueError("Invalid controller flags")
    state["last_ms"] = t
    if gap:
        actions = ["gap"] + (["abort"] if state["phase"] != "idle" else [])
        return dict(initial_state(), last_ms=t), actions
    actions = []
    if state["phase"] == "idle":
        if busy is True:
            state.update(phase="busy", busy_since=t, rest_since=None, burst_taken=False)
            actions = ["start", "select_pre_contact"]
            if valid:
                actions.append("select_hand_busy")
    elif t - state["busy_since"] >= MAX_EPISODE_MS:
        return dict(initial_state(), last_ms=t), ["gap", "abort"]
    if state["phase"] != "idle":
        if busy is True:
            state.update(phase="busy", rest_since=None)
            if motion is True and valid and not state["burst_taken"]:
                actions.append("select_carry")
                state["burst_taken"] = True
        elif busy is False and motion is False and valid and t - state["busy_since"] >= BUSY_MIN_MS:
            if state["rest_since"] is None:
                state.update(phase="settling", rest_since=t)
                actions.append("select_release")
            elif t - state["rest_since"] >= REST_MIN_MS:
                return dict(initial_state(), last_ms=t), actions + ["select_rest", "finish"]
        else:
            state.update(phase="busy", rest_since=None)
    return state, actions


def replay(samples: list[dict]) -> list[dict]:
    """Run step() over a whole trace from the initial state.

    Returns one record per sample, in order: {"t_ms": int, "actions": [...],
    "phase": <phase after the step>}. The machine above is unchanged; this is only
    the entry point the tester diffs against the browser port
    (phone/assets/controller.js replay). An invalid sample raises the same
    ValueError step() raises, at the sample that is invalid; nothing is swallowed.

    Trace boundary rule (coordinator, 2026-10-08): JSON text 100.0 is accepted as
    100 at the trace boundary; step() itself still requires int. An integral float
    t_ms is normalised to int in a copied sample so both CLIs agree (JS cannot
    distinguish 100.0 from 100); a non-integral float (100.5) still raises
    "Invalid controller time".
    """
    if not isinstance(samples, list):
        raise ValueError("Controller trace must be a list of samples")
    state = None
    log = []
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError("Invalid controller sample")
        t = sample.get("t_ms")
        if isinstance(t, float) and not isinstance(t, bool) and t.is_integer():
            sample = dict(sample, t_ms=int(t))
        state, actions = step(state, sample)
        log.append({"t_ms": sample["t_ms"], "actions": list(actions), "phase": state["phase"]})
    return log


def _main(argv: list[str]) -> int:
    """`python -m perception.episode_controller trace.json`

    trace.json is either a JSON list of samples or an object with a "samples" key.
    Prints replay() as compact JSON (sort_keys, no spaces) so the output can be
    diffed byte-for-byte with the Node replay. A ValueError prints its message to
    stderr and exits 1; a missing file prints "error: trace file not found" and an
    unreadable or undecodable file "error: trace file is not valid JSON" (both
    exit 1, the same text as the Node CLI); a usage error exits 2.
    """
    import json
    import sys
    if len(argv) != 2:
        sys.stderr.write("usage: python -m perception.episode_controller trace.json\n")
        return 2
    try:
        with open(argv[1], "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        sys.stderr.write("error: trace file not found\n")
        return 1
    except (OSError, ValueError):  # unreadable, undecodable text, or JSONDecodeError
        sys.stderr.write("error: trace file is not valid JSON\n")
        return 1
    samples = data.get("samples") if isinstance(data, dict) else data
    try:
        result = replay(samples)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv))
