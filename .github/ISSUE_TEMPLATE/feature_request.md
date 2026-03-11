---
name: Feature request
about: Suggest something the package should be able to do
title: ''
labels: enhancement
assignees: ''
---

**The problem you are trying to solve**

Describe the situation, not the solution. "I cannot onboard a source that
reports durations in milliseconds" is more useful than "add a milliseconds
option".

**Why it belongs in sqmine rather than in your own code**

The package is deliberately small. Ingestion, features and label agreement are
in scope; modelling, storage and dashboards are not.

**Does it touch the schema or the privacy boundary?**

- [ ] It changes `Episode`
- [ ] It changes where or how pseudonymisation happens
- [ ] It adds a runtime dependency
- [ ] None of the above

If any of the first three are ticked, please read the corresponding section of
CONTRIBUTING.md before writing code.

**Anything else**
