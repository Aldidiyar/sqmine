# Contributing

Thanks for taking an interest. This is a small research package, so the bar is
less about process and more about not breaking the two things that have to stay
true: the canonical schema, and the privacy boundary.

## Getting set up

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Before opening a pull request

Run what CI runs:

```bash
ruff check .
ruff format --check .
python -m mypy
python -m pytest --cov=sqmine --cov-fail-under=90
```

All four must pass. Coverage is currently 100% and should not go down without a
reason stated in the pull request.

## Things that need discussion first

Open an issue before writing code if your change touches any of these:

- **`sqmine/schema.py`.** The canonical `Episode` is a contract. Changing it
  invalidates every stored episode, every feature table and every model trained
  on them. Additive, optional fields are usually fine; anything else needs a
  schema version bump and a migration note.
- **`sqmine/privacy.py`.** Pseudonymisation happens in exactly one place, at the
  adapter boundary. Moving it, making it optional, or adding a second path into
  the canonical store defeats the point of having a boundary at all.
- **New runtime dependencies.** The package deliberately has none. See the
  README for why. A dependency is not forbidden, but it has to earn its place.

## Adding a source adapter

Most contributions will be adapters, and they are meant to be easy:

1. Subclass `SourceAdapter` in `src/sqmine/adapters/`.
2. Set `name` and `default_mapping`.
3. Implement `read_rows` and `build_episode`. Do **not** override `load`: it
   fixes the order of operations so no adapter can skip pseudonymisation.
4. Decorate with `@register_adapter`.
5. Export it from `adapters/__init__.py`.
6. Add tests covering the happy path, at least three rejection reasons, and one
   assertion that no raw identifier survives into the episode.

## Style

- `ruff` decides formatting and import order. Do not argue with it in review.
- Public functions and classes get a docstring that says *why*, not *what*. The
  signature already says what.
- Tests are named for the behaviour they pin, not the function they call:
  `test_second_contact_within_the_window_is_a_repeat`, not `test_extract_2`.

## Reporting a security or privacy issue

Do not open a public issue for anything involving real personal data. Contact
the maintainer directly and include no sample data in the message.
