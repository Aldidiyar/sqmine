# sqmine

[![CI](https://github.com/OWNER/sqmine/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/sqmine/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Service-quality episode processing for data-mining research.

`sqmine` turns service-episode records from unrelated source systems into one
canonical, pseudonymised form, derives reproducible features from it, and
scores the inter-annotator agreement of the labelled corpus those features will
be trained against.

It is the data-preparation core of a doctoral project on assessing service
quality with data-mining methods. It is deliberately small: it does the three
things that have to be correct before any modelling is worth starting.

---

## Why this exists

Service quality is usually judged from periodic surveys, which suffer from low
and biased response rates, plus manual review of well under one percent of
interactions. The alternative is to score every episode from data the
organisation already produces. That turns out to be mostly a data-preparation
problem:

1. **Five source systems, five vocabularies.** The CRM calls it `TRX_ID` and
   stores a duration in minutes. The contact centre calls it `call_uuid`,
   stores seconds, and nests the customer inside a `party` object.
2. **The data is personal.** Transcripts contain names, phone numbers and
   national identification numbers, inline, in the middle of sentences.
3. **The labels are human, so they disagree.** A model trained on a corpus two
   annotators cannot agree on will learn their disagreement.

`sqmine` addresses those three, and stops there.

## Install

```bash
git clone https://github.com/OWNER/sqmine.git
cd sqmine
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Python 3.10 or newer. There is nothing else to install.

## Quick start

```bash
# A key is required. Generate one once, keep it out of the repository.
python -c "import secrets,pathlib; pathlib.Path('pseudonymisation.key').write_bytes(secrets.token_bytes(32))"

# 1. Normalise a source export into canonical episodes
sqmine ingest examples/crm_sample.csv \
    --adapter crm-csv \
    --tenant pilot-bank \
    --key-file pseudonymisation.key \
    --out episodes.jsonl

# 2. Derive features
sqmine features episodes.jsonl --out features.csv --stats

# 3. Check whether the labelling round can be accepted
sqmine agreement examples/labels_sample.csv --col-a annotator_a --col-b annotator_b
```

`ingest` and `agreement` both act as quality gates: they exit with code `2`
when the acceptance rate or the kappa falls below the threshold, so they can be
wired straight into a pipeline without parsing their output.

## What it does

### Canonical episode record

Every source is translated into one frozen, validated record
(`sqmine.schema.Episode`). Validation is not advisory: a record whose closing
timestamp precedes its opening timestamp, or whose timestamps carry no time
zone, cannot be constructed at all.

The schema is the contract the whole package is organised around. It is the one
part designed **not** to change: everything downstream, including stored
episodes and trained models, is invalidated when it does.

### Source adapters

`SourceAdapter` is a port; each adapter is a plug for one source system.
Adapters are the only code that knows an external field name exists.

```python
from sqmine.adapters import CrmCsvAdapter
from sqmine.privacy import Pseudonymiser

adapter = CrmCsvAdapter("pilot-bank", Pseudonymiser.from_file("pseudonymisation.key"))
result = adapter.load("examples/crm_sample.csv")

print(result.summary())        # 3/3 rows accepted (100.0%), 0 rejected
print(result.episodes[0].handling_seconds)
```

A malformed row is collected as a `Reject` with its index and reason rather
than raised: one bad row in a nightly export must not abort the batch, and must
not disappear silently either.

Adding a source means writing an adapter. Onboarding a second organisation with
the same source types means passing a different `mapping`, with no code change:

```python
CrmCsvAdapter("second-org", pseudonymiser, mapping={"episode_id": "ID_TRANSACTION"})
```

### Pseudonymisation at the boundary

Identifiers are replaced with a keyed HMAC-SHA256 digest **inside the adapter**,
before a record is constructed. There is exactly one place where personal data
crosses into the system, which is the only arrangement an auditor can check
cheaply.

The mapping is deterministic, so the same customer always yields the same
reference and episodes can still be linked for churn and repeat-contact
analysis. It is not reversible without the key.

> This is pseudonymisation, not anonymisation. Under most data-protection
> regimes, including the Republic of Kazakhstan's Law No. 94-V, the result is
> still personal data and the obligations still apply. Keep the key in a
> different trust domain from the data.

Free text gets a second pass, because field-level replacement does nothing for
`"my number is 701 234 56 78"`. `redact_text` substitutes typed placeholders for
emails, card numbers, national identification numbers and telephone numbers.
Named-entity redaction is **not** implemented; see [Limitations](#limitations).

### Features

`extract_features` is pure and order-stable. It sorts by opening time itself
rather than requiring sorted input, because unsorted input would otherwise
produce plausible-looking but wrong repeat-contact counts, which is the kind of
defect that survives review.

### Inter-annotator agreement

`score_agreement` reports observed agreement, Cohen's kappa, the Landis and Koch
descriptive band, and a pass/fail verdict against a threshold (0.70 by default).

Degenerate cases are handled explicitly: when both annotators assign a single
label to everything, expected agreement is 1.0 and kappa is undefined. The
convention here returns 1.0 for identical constant labelling and 0.0 otherwise,
so a corpus with no variance cannot pass the gate by accident.

## Why there are no dependencies

The core is standard library only. `pandas` would have made `features.py`
shorter, and was not used, for three reasons:

1. **Reproducibility.** A research result has to be regenerable years later.
   Every dependency is a version that can change behaviour underneath a
   published number.
2. **Cost of the environment.** The project runs on a fixed grant budget with no
   dedicated operations role. A dependency-free package installs in seconds in
   CI and anywhere else.
3. **Nothing here needs it.** The workload is a nightly batch of roughly 1,300
   episodes. The constraint is correctness, not throughput.

Development dependencies are a different matter and are pinned by floor in
`[project.optional-dependencies]`.

## Development

```bash
ruff check .          # lint
ruff format --check . # formatting
python -m mypy        # strict type checking
pytest --cov=sqmine --cov-report=term-missing
```

CI runs all four on Python 3.10, 3.11 and 3.12, plus a package build, and fails
under 90% line coverage. See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Project layout

```
src/sqmine/
├── schema.py                      canonical Episode, validation, timestamps
├── privacy.py                     HMAC pseudonymisation, text redaction
├── features.py                    deterministic feature extraction
├── agreement.py                   Cohen's kappa and the acceptance gate
├── cli.py                         ingest / features / agreement
└── adapters/
    ├── base.py                    the port: SourceAdapter, LoadResult, registry
    ├── crm_csv.py                 CSV transaction-log adapter
    └── contact_centre_json.py     JSON call-record adapter
```

## Limitations

These are known and deliberate, not oversights:

- **Text redaction is pattern-based.** It catches emails, card numbers,
  national identification numbers and phone numbers. It does **not** catch
  names, addresses or account numbers written in words. Do not treat redacted
  transcripts as safe to share outside the trust boundary.
- **No model training.** Scoring models live in a separate component. This
  package prepares their input and gates their labels.
- **Single-process.** There is no distributed execution and none is planned at
  this scale.
- **Repeat-contact window is fixed** at 30 days (`REPEAT_CONTACT_WINDOW`). It
  should become tenant configuration; tracked as an issue.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and feature requests use the
templates in [`.github/ISSUE_TEMPLATE`](.github/ISSUE_TEMPLATE).

## Licence

MIT. See [LICENSE](LICENSE).

## References

- Cohen, J. (1960). A coefficient of agreement for nominal scales.
  *Educational and Psychological Measurement*, 20(1), 37–46.
- Landis, J. R., & Koch, G. G. (1977). The measurement of observer agreement for
  categorical data. *Biometrics*, 33(1), 159–174.
- Cockburn, A. (2005). *Hexagonal Architecture (Ports and Adapters).*
- Wirth, R., & Hipp, J. (2000). CRISP-DM: Towards a standard process model for
  data mining.
