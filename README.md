# PAM memory layer

The object-memory layer for PAM (Physical Assistive Memory): an elder-care wearable that
notices when the wearer sets something down, remembers where, and answers "where did I
put my glasses?" by voice with a photo of the spot.

Split out of the HackMIT 2026 `hackmit` repo on 2026-10-05. That repo is the archive;
this one is where the memory layer lives from now on.

## Read first

`docs/MEMORY_SYSTEM_V4.md` is the canonical spec. Part 1 is the design; Part 2 is the
review log. Where they differ, Part 1 wins. Section 10 of Part 1 is the build order.

## Layout

| Path | What |
| --- | --- |
| `perception/` | Capture, hand-interaction episodes, object and personal memory ledgers, VLM and voice helpers, tests |
| `phone/` | The browser test rig: the camera page an iPhone runs in Safari, served over HTTPS by `serve.py` |
| `server/` | The FastAPI service the phone streams to: object memory API, camera relay, tests. `app.py` still carries routes from the full elder-care app and is being trimmed (spec, section 10). |
| `docs/` | The spec |

## Running the tests

```
pip install -r perception/requirements.txt -r server/requirements.txt
python -m unittest perception/test_capture.py perception/test_interaction.py
python -m unittest server/test_memory_lifecycle.py server/test_personal_pipeline.py
```

## Secrets and weights

`phone/serve.py` needs `phone/cert.pem` and `phone/key.pem` for HTTPS (Safari will not
open the camera on plain HTTP). Generate them locally; they are ignored by git and must
never be committed. Model weights are shared out of band and ignored the same way.
