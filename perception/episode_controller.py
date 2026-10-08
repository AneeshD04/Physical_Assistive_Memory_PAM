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
