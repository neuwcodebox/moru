# AGENTS.md

## Project

Moru is a local, conversational image-generation desktop app.

Users describe or revise an image in natural language. A local prompt LLM converts the request into an image-generation prompt, and the local Anima backend generates the image. The UI is a React web UI hosted inside a Python desktop application.

Read these before making non-trivial changes:

- `docs/SPEC.md`: product behavior and requirements. This is the source of truth for **what** Moru must do.
- `docs/TECH.md`: architecture and implementation guidance. This is the source of truth for **how** Moru is currently intended to be built.
- If they conflict, preserve the behavior required by `SPEC.md` and call out the technical conflict.

Do not invent product behavior that is not required by `SPEC.md`.

## Development

- Python environment and dependencies are managed with `uv`.
- Use `uv sync` to restore the locked Python environment.
- Run Python commands through `uv run ...`.
- Keep `uv.lock` in sync with `pyproject.toml`.
- Do not add dependencies when the standard library or an existing dependency is sufficient.
- Do not commit model binaries, generated images, local databases, logs, build outputs, or secrets.
- Treat React build artifacts as generated files; edit their source instead.

## Engineering principles

Write the smallest clear design that satisfies the requirement. Follow SOLID, KISS, YAGNI, and DRY without turning them into speculative abstraction.

### SOLID

- **Single Responsibility:** each module, class, component, and function should have one cohesive reason to change. Split code that mixes UI, persistence, inference, process management, or domain behavior.
- **Open/Closed:** introduce extension points only where the project actually has multiple implementations or a known boundary. Do not create plugin systems or generic frameworks for hypothetical future needs.
- **Liskov Substitution:** implementations must honor the behavioral contract of the abstraction they implement. Do not require callers to know implementation-specific exceptions.
- **Interface Segregation:** prefer small, focused interfaces/protocols over large manager objects.
- **Dependency Inversion:** application logic should depend on narrow abstractions at external boundaries. Keep pywebview, ComfyUI, llama.cpp, filesystem, and SQLite details out of unrelated business logic.

### Clean code

- Prefer explicit data flow and simple control flow.
- Use precise names. Avoid vague names such as `manager`, `helper`, `utils`, `data`, or `handle` when a specific concept exists.
- Keep functions focused and short enough to understand without tracing unrelated state.
- Avoid hidden global state and action-at-a-distance.
- Prefer immutable records for persisted generation history; changes create new records/Forks rather than mutating history.
- Keep side effects at boundaries. Separate decision logic from I/O where practical.
- Comments explain **why**, constraints, or non-obvious tradeoffs; do not narrate obvious code.
- Never silently swallow exceptions or silently fall back to a different model/behavior.
- Do not refactor unrelated code while implementing a focused requirement.
- Do not add abstractions solely because they may be useful later.

Before adding a new abstraction, be able to name the concrete duplication, coupling, or variation it removes.

## Architecture boundaries

Keep these concerns separable:

- UI/rendering
- application/use-case logic
- prompt generation
- image generation
- persistence/history
- external runtime/process integration

The conversation/Fork model is application behavior. It must not depend directly on React, pywebview, ComfyUI node internals, or llama.cpp APIs.

Wrap external engines behind narrow project-owned interfaces so they can be tested without loading models or a GPU.

## Testing

Tests are executable requirements, not implementation snapshots.

### Required qualities

Tests must be:

- **Fast:** ordinary unit tests must not load AI models, require a GPU, access the network, launch ComfyUI, or wait on real time.
- **Deterministic:** control randomness, clocks, IDs, and external responses where they affect assertions. Avoid sleeps and timing-dependent assertions.
- **Independent:** tests may run in any order and must not rely on state left by another test.
- **Readable:** a failing test should make the expected behavior obvious.
- **Focused:** each test should primarily fail for one behavioral reason.
- **Maintainable:** test public behavior and stable contracts rather than private implementation details.
- **Requirement-aligned:** every changed requirement or user-visible behavior must have a corresponding test or an explicit reason why automated testing is unsuitable.

### Test design

- Name tests after behavior, not the function being called.
- Prefer Arrange–Act–Assert or an equally clear structure.
- Use lightweight fakes/stubs at external boundaries. Mock interactions only when the interaction itself is the contract.
- Do not duplicate production algorithms inside tests to compute expected results.
- Do not assert incidental details such as exact internal call order unless required behavior depends on it.
- A bug fix should include a regression test that fails before the fix and passes after it.
- When `SPEC.md` behavior changes, update the relevant tests in the same change.
- Keep integration tests separate from unit tests.
- Tests requiring real models/GPU belong in an explicitly marked integration/smoke suite and must not slow the normal unit-test loop.

For Moru in particular, unit-test the conversation tree, Fork semantics, prompt-create/refine decisions, settings validation, persistence behavior, and failure handling without inference engines.

### Running tests

- Run the narrowest relevant tests while developing.
- Before declaring Python changes complete, run the full normal suite with `uv run pytest`.
- Run frontend checks/tests defined by `frontend/package.json` when frontend code changes.
- GPU/model smoke tests are additional validation, not a replacement for unit tests.

Do not weaken, delete, or skip a valid test merely to make the suite pass.

## Change workflow

1. Read the relevant requirement and surrounding code before editing.
2. Identify the smallest coherent change.
3. Add or update tests that express the required behavior.
4. Implement the change while respecting existing project boundaries.
5. Run focused tests, then the relevant full suite.
6. Review the diff for accidental complexity, unrelated edits, dead code, and stale documentation.

For substantial architecture changes, explain the tradeoff before replacing an established project pattern.

## Definition of done

A change is done only when:

- it satisfies the relevant `SPEC.md` behavior;
- the implementation remains consistent with `TECH.md`, or the necessary documentation change is included;
- relevant automated tests cover the behavior and pass;
- normal tests remain fast and deterministic;
- no unnecessary dependency, abstraction, or unrelated refactor was introduced;
- failure paths are explicit rather than silently ignored;
- the code is understandable without relying on the agent's conversation history.

Working code is required. Plausible-looking code without verification is not complete.
