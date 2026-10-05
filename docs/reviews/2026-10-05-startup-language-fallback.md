# Startup language fallback

The saved display language is loaded through get_language before the main bootstrap payload.
A failed model-status or project load can therefore display an error in the saved language.
If the preference cannot be read, is unsupported, or has not yet arrived, the UI uses English.
Native startup dialogs also use English when reading the saved preference fails.
Normal first-run Korean and an explicitly saved Korean selection remain unchanged.

Addresses https://github.com/neuwcodebox/moru/pull/1#discussion_r4180054447.

Verification:
- Frontend: 86 tests passed, including English/Korean bootstrap failures and unavailable/unsupported preferences; TypeScript and production build passed.
- Python language tests: 27 passed, including language retrieval independent of model-status failure and English native fallback for an unreadable database.
- Full Python suite: 212 passed, 1 skipped, and the same 2 baseline Windows Job lifecycle failures previously reproduced on Linux.
- No workflows, merge, deployment, or unrelated behavior changes.
