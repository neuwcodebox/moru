# Korean and English localization review

## Scope and design

- Added i18next and react-i18next, with all Korean/English JSON resources bundled in the offline UI.
- Added a compact language selector beside the upper-left logo. The saved preference comes from bootstrap and is persisted separately from generation settings. New installations retain Korean; unsupported saved values and missing translations fall back to English.
- Localized main UI, accessible names, progress, settings, model management, prompt editor, viewer, native startup messages and model file filters. User requests, prompts, filenames and model brand names stay unchanged.
- Retain stable error codes until render, so saved and existing errors follow language changes. Unknown bridge errors use safe translated messages.
- Added English README.md and Korean README.ko.md with reciprocal links immediately under their H1 headings. Updated SPEC and TECH, and included new runtime dependency licenses in portable packaging.

## Verification

- Frontend: 82 tests passed across 8 files; TypeScript check and production build passed.
- Python: 209 passed, 1 skipped, 2 pre-existing Windows Job lifecycle failures on Linux. Both failures also reproduce against untouched base commit afffcb30fb720b113cf5dd9619370a58caa35bc0.
- Ruff and git diff whitespace checks passed.
- Tests cover persistence and unsupported saved language, failed saves, switching without losing draft/project content, startup race prevention, translating an existing error, translated dialogs/model errors, and safe bridge errors.
- Review found and fixed an early-bootstrap language-selection race and an error banner being cleared by language selection.
- No CI or GitHub Actions workflows were added. GPU inference, Windows WebView2 and portable executable execution were not run in this Linux environment.
- Independent source review found no remaining blockers. Browser visual checking was unavailable because Chromium could not launch within the sandbox (socket permission); layout has source review and DOM tests only.
- Baseline failures: `test_restarting_an_exited_worker_releases_its_pipes_and_windows_job` and `test_progress_callback_failure_stops_the_worker_and_has_a_stable_error` in `tests/test_worker_lifecycle.py`.
