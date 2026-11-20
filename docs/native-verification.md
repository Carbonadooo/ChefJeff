# Native port verification report

> Historical v1.0 report. The native 1.1 decision/art update is documented in [native-decision-art.md](native-decision-art.md); see `native-verification-v1.1.md` for its CPU-only checkpoint, and `native-verification-v1.1.1.md` for completed real-window verification.

Verified on Windows with CPython 3.12.11 (Miniforge base interpreter), isolated `.venv`, Pygame 2.6.1 and SDL 2.28.4. Upstream checkout: `35c77092f93fa6d1a9b94a59fcd3ba6c53948f3a`. Adapter version: `1.0.0`. Date: 2026-11-15 UTC.

The implementation is in a new dedicated `D:\Desktop\IRL\ChefJeff` checkout. No previous ChefJeff checkout was found in the inspected IRL tree. Existing `overcooked-pr2`, Assignment and other IRL projects were not edited. No reset, clean, original implementation deletion, commit or push was performed. The only modified pre-existing tracked file is `.gitignore`; all implementation and documentation files are additive.

## Results

| Check | Actual result |
|---|---|
| Portable original engine + native regression runner | **329 tests run, OK, 2 skipped**; final run 49.891 s |
| Focused native tests | All 7 passed, included in the 329-test final run |
| Headless import boundary | Reset, step and English state work; no `pygame`, `web_server` or `jev` import |
| Real native window | Started successfully, visibly inspected with computer-use screenshot; live board, chefs, countdown and expiry/negative score displayed |
| Real SDL event/render check | **PASS**, driver `windows`; real window rendered; synthetic two-player keydown/keyup/diagonal and focus-loss verified; dummy driver explicitly rejected |
| Final ordinary-kitchen recording/replay | **Verified**: 180 s, 3,600 ticks, score 500, 10 served; 3,601 boundaries and **413 raw engine events** matched |
| Final split-kitchen recording/replay | **Verified**: 180 s, 3,600 ticks, score 60, 2 served; 3,601 boundaries and **306 raw engine events** matched |
| Burger / multi-recipe rounds | Level 2: score 313, 4 burgers; Level 3: score 440, 7 dishes, both burger and steak served |
| Recording tamper/incompleteness checks | Changed raw events and score detected; missing final record reported incomplete |
| Source path with spaces / different working directory | Headless startup and final steak replay passed from `%TEMP%\ChefJeff Native Space Check` while cwd was `%TEMP%` |
| Byte compilation | New package, entrypoint, check scripts and focused test compiled successfully |
| Required release audit | **PASS**: 850 tracked files, 5,066 historical blobs, zero findings |
| Whitespace / repository hygiene | `git diff --check` passed; no project `logs/` directory created |

The split-kitchen trace includes 25 throws, 24 landings, 15 floor pickups, one catch, preparation/cooking, two deliveries, plate return/wash, expiry, burn/fire/spread and natural round closure. These are the original engine events, not a renderer approximation. The reference driver was corrected to use the repository's existing `_cell_side` runner/maker assignment on the split floor.

The original release-audit command completed successfully. A second run of the same unchanged audit function with batched read-only Git object access produced identical results; it was used to avoid waiting on thousands of Windows process launches. Its audit scope remains tracked files and reachable Git history, as stated by upstream.

## Exact final replay evidence

```json
{
  "verified": true,
  "episode_id": "f05d72217744446289a6e9e71a02d621",
  "boundaries_checked": 3601,
  "engine_events_checked": 413,
  "tick": 3600,
  "time": 180.0,
  "score": 500,
  "served": 10,
  "state_sha256": "2d257cd8d2370dbf34a6239dbcf5e75887055219a08af5a3981d5e2cf7c17f04",
  "end_reason": "round_complete"
}
```

```json
{
  "verified": true,
  "episode_id": "ca55756d0c6646f7afe9b3b883e7b170",
  "boundaries_checked": 3601,
  "engine_events_checked": 306,
  "tick": 3600,
  "time": 180.0,
  "score": 60,
  "served": 2,
  "state_sha256": "5ed48e021811db61a9df6d4d7b08eb465f42dddfc32505975c5a8165fa334bae",
  "end_reason": "round_complete"
}
```

The sample logs are `native-recordings/sample-final-steak.jsonl` and `native-recordings/sample-final-split.jsonl`. They include full frozen configuration, seeds/map/recipes, exact applied inputs, raw events, per-boundary digests and final provenance/state. They are local generated evidence excluded by `.gitignore`, and remain on disk. Development logs are retained, but older fingerprints may require diagnostic `--allow-code-change`; the final samples match the delivered source.

## Broader upstream checks and limitations

The repository-required `python -m unittest discover -s tests` was actually run on the original suite: **909 tests, 19 failures, 62 errors, 5 skipped** (300.635 s). Many service/deployment modules require unavailable Unix `fcntl` or `pwd`; some tests require symbolic-link privileges or POSIX permission bits. Other failures concern the original web session/controller expectations and package subprocess encoding. They were not hidden or fixed by changing the web game. The full run was launched before the new native test file was added; the final native/core runner separately covers the final port.

For baseline evidence, an untouched HEAD archive was extracted into a separate temporary folder and `test_facing_controls.py` was run there: 17 tests, one existing error in `ShortActionMoveTests.test_a_move_during_a_short_take_starts_after_it` (`job` is `None`). This reproduces a representative failure without any native code being present. It does not claim that every full-suite failure was individually reproduced.

The required `node tests/hosted_browser_test.cjs` failed with Node 24.22.1: its TypeScript harness reached `SyntaxError: Cannot use import statement outside a module`. The same error reproduced in the untouched archive. That browser test remains unresolved and is independent of native gameplay; the original browser source was left unchanged.

Physical keyboard input is **not claimed verified**. Computer-use successfully raised and captured the real window, but its injected keys did not appear in the SDL action journal. Synthetic events in a real SDL window and headless held/edge/release state passed. The concise physical-keyboard/focus-switch checklist is in `native-desktop.md`. Hardware rollover and a complete manually played GUI meal remain manual acceptance steps.

The render loop and recording are local and single-threaded. A crash/power loss may leave a flushed prefix without a final row; replay verifies the available prefix and reports the file incomplete. It does not silently infer a successful finish. Logs can grow during long rounds because they preserve exact inputs/events. Replay matches engine events, key state, score/reward and provenance; it does not promise identical pixels.

## Deliverables and next steps

See `native-desktop.md` for installation, exact PowerShell start/replay/test commands, all controls, API usage, recording fields and scope. The gameplay runtime has only one external dependency, Pygame; test-only NumPy/Pillow are separate upstream requirements. Original placeholder geometry is used, with no copied game assets.

The playable offline loop, original mechanics, second keyboard, agent interface and exact local replay are implemented. The immediate next step is the five-step manual physical-keyboard check. Optional later work includes polished assets/audio, in-window level/restart selection, a packaged executable and embedding a nonblocking agent poll loop in the native presentation. None is required to launch the current local game.
