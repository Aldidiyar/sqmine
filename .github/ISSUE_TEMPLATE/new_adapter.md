---
name: New source adapter
about: Request or propose support for another source system
title: 'Adapter: '
labels: adapter
assignees: ''
---

**Source system**

**Format** (CSV, JSON, database export, API)

**Sample record, with every identifier replaced by a synthetic value**

```
paste here
```

**Mapping to the canonical schema**

| Canonical field | Source field | Notes |
|---|---|---|
| episode_id |  |  |
| customer_id |  |  |
| opened_at |  |  |
| closed_at or duration |  |  |
| wait_seconds |  |  |
| channel |  |  |
| service_type |  |  |
| outcome |  |  |
| operator_id |  |  |
| text |  |  |

**Fields the source does not have**

An adapter often has to derive or default a field. Say which ones, and what the
source does provide instead.
