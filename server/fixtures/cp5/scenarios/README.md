# CP5 scripted scenarios (tester, 2026-10-10)

One JSON per case, run by `perception/scenario_runner.py` (Builder A; the schema is its
module docstring, the same text as `scripts/scenario_example.json`) through
`server/test_cp5_scenarios.py` and `scripts/run_scenarios.py`. Every file carries the
same `basis` string: these are **software-correctness expectations on synthetic data,
never accuracy claims**. Nothing here was measured on a camera.

Shape: `{"name", "basis", "clock_start_ms", "description", "identity"?, "items": {handle:
{label, tag, medication?}}, "steps": [...]}` with the runner's step kinds `episode`,
`idle`, `correction`, `gap`, `advance`, `query`. A query step's `expect` is
`{"outcome", "shape"}` (the rubric outcome and the answer shape); the tester's extra
keys `expected_basis` (tokens that must appear in the answer's `basis`),
`expected_index_pending` and `expected_gap_ms` are read by `server/test_cp5_scenarios.py`
and ignored by the runner. `truth.item` is a handle the runner resolves to the store's
item id; explicit rubric truth keys override the scene's derived truth (the containment
scenario needs that, because the synthetic scene does not model containment).

The seven mandatory cases (Part 1 section 10 item 5) plus the medication set:
`new_item_before_indexing`, `fast_put_down`, `caregiver_relocation_observed`,
`unobserved_relocation_then_sighting`, `two_refills_lookalikes`, `coverage_loss`,
`medication_set`; `containment_keys_in_basket` is the extra Part 1 case 5.
