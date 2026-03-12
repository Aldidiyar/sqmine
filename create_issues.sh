#!/usr/bin/env bash
# Seed the repository's issue tracker. Run once, after the first push.
# Requires the GitHub CLI: https://cli.github.com/
set -euo pipefail
command -v gh >/dev/null || { echo "install the GitHub CLI first" >&2; exit 1; }

gh label create adapter       --color 0e8a16 --description "New or changed source adapter" --force
gh label create privacy       --color d93f0b --description "Touches the pseudonymisation boundary" --force
gh label create good-first-issue --color 7057ff --description "Small, self-contained" --force

gh issue create --title "Make the repeat-contact window tenant configuration" \
  --label enhancement,good-first-issue --body \
'REPEAT_CONTACT_WINDOW in features.py is hard-coded to 30 days.

Thirty days is right for the pilot organisation because its billing cycle is
monthly. It will be wrong for an organisation whose service cycle is quarterly,
and transferability is a project requirement rather than a nice-to-have.

Proposal: move the window into tenant configuration, keeping 30 days as the
default so existing callers are unaffected.

Acceptance: a tenant can set the window without a code change, and the existing
feature tests still pass unmodified.'

gh issue create --title "Named-entity redaction for transcripts" \
  --label enhancement,privacy --body \
'redact_text() is pattern-based. It catches emails, card numbers, national
identification numbers and telephone numbers. It does not catch names,
addresses, or account numbers written in words, and the README says so.

This is the largest known gap in the privacy boundary. A transcript redacted by
the current implementation must not be treated as safe to share outside the
trust boundary.

Likely approach: an optional extra that pulls in a named-entity recogniser,
kept out of the core so the package stays dependency-free by default.

Acceptance: a held-out set of synthetic transcripts containing names and
addresses is redacted with recall reported, and the README limitation is
updated with the measured figure rather than removed.'

gh issue create --title "Adapter: complaints register (Excel export)" \
  --label adapter --body \
'The complaints register is the third source named in the project plan and has
no adapter yet.

It is awkward in a way the existing two are not: the export has no closing
timestamp at all, only a date, and every record is by definition an escalation.
The adapter will have to derive closed_at and default outcome, which makes it a
good test of whether the adapter layer really absorbs source messiness.

Acceptance: an adapter, a mapping table in the issue template format, tests
covering at least three rejection reasons, and a test that no raw identifier
reaches the episode.'

gh issue create --title "Report Krippendorff's alpha alongside Cohen's kappa" \
  --label enhancement --body \
'Cohen kappa handles exactly two annotators and no missing judgements. The
annotation plan has two annotators per item, so it is adequate today.

It stops being adequate as soon as a third annotator adjudicates disagreements,
which the plan calls for at the second labelling round. Krippendorff alpha
handles any number of annotators and missing values.

Acceptance: alpha computed for nominal data, agreeing with kappa to three
decimal places on two-annotator complete data, which is a property the
implementation can be tested against.'

gh issue create --title "Document the key-rotation procedure" \
  --label documentation,privacy --body \
'Pseudonymisation references are deterministic under a key. Rotating the key
changes every reference, which silently breaks linkage across historical
episodes: the same customer before and after rotation looks like two people.

There is currently no documented procedure and no warning in the README.

At minimum the documentation should state that the key cannot be rotated
without re-ingesting history, and that the key must be stored in a different
trust domain from the data.'

echo "done"
