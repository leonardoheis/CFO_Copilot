---
name: code-structure
description: Deciding which layer a piece of logic belongs in when several flows share the same mechanics — what stays in the handler that owns the business rule, and what moves into a shared service. Use when the same operational block is copy-pasted across callers, when a bug fixed in one flow is still live in another, or when a new feature reuses mechanics an existing one already has. Triggers on "which layer", "where does this logic belong", "shared service or handler", "duplicated across flows", "extract shared mechanics".
---

# Service Layer Structure

## Overview

**Two-layer separation:** handlers orchestrate domain rules (the "why/when"),
while a service layer centralizes reusable operational mechanics (the "how").

The payoff is that a fix lands once. When the same operation is inlined in
four flows, the fourth one keeps the bug after you have fixed three.

## Core pattern

```
Orchestration (route handlers, CLI commands, jobs)   Service layer
├── owns business rules                              ├── owns reusable operations
├── owns state transitions                           ├── owns provider/SDK interaction
├── owns auth and ownership checks                   ├── owns retry and timeout details
├── owns failure classification                      ├── owns health/readiness checks
├── owns the user-facing error                       └── returns structured results
└── calls service functions
```

**Rule of thumb:**
- "What this product flow means" → keep in the handler
- "How to do this operation reliably" → move to a service

## Quick reference

| Design principle | Do | Don't |
|---|---|---|
| API shape | Composable capability functions | One giant "do everything" method |
| Inputs/outputs | Explicit parameters, structured returns | Hidden global state, reaching into the DB |
| Migration | Extract one block, move one caller, verify, then the rest | Refactor every caller at once |
| Domain logic | Keep auth, policy, error classification in the handler | Let a service mutate domain state directly |
| Extraction trigger | Logic repeated across 2+ callers | Logic used once — that is over-abstraction |

## Designing service functions

Design as **capability blocks**, not monoliths, so each caller takes only the
steps it needs:

```python
# Good: composable — a backfill job and an API request use different subsets
fetch_raw_quotes(ticker, *, session)
normalize_quotes(payload)
adjust_for_splits(quotes, splits)
persist_panel(frame, *, path)
```

Each function should:

- accept everything it needs as **explicit parameters**, so it can be called
  from a test without standing up the world
- return **structured results** (a dataclass or Pydantic model, not a bare
  tuple whose fields you have to count)
- never reach into the database or global state directly
- make failure explicit — return an empty result for "nothing found" and raise
  only for genuine failures, so callers are not forced into `try/except` as
  control flow

## Migration checklist

1. Write the flow inline in the handler first, so the behaviour is clear
2. Mark the operational chunks that repeat across callers
3. Extract **only** the repeated, non-domain chunks
4. Move one caller → verify → move the rest
5. Keep domain policy in the handler (auth, status transitions, error mapping)
6. Run the project's typecheck, lint and tests before moving the next caller

## Anti-patterns

| Anti-pattern | Problem |
|---|---|
| **God service** | One huge function hides all the control flow |
| **Leaky service** | The service writes to tables the handler is supposed to own |
| **Inconsistent API** | Every function takes a different argument style and signals errors differently |
| **Over-abstraction** | Extracting logic that has exactly one caller |

## Example: a notification used by two flows

```python
# services/notifications.py — shared mechanic, knows HOW
def send_welcome(email: str, name: str) -> None:
    body = render_template("welcome.html", name=name)
    email_client.send(to=email, subject="Welcome", html=body)


# api/routes/signup/endpoints.py — orchestration, owns WHEN
if user.marketing_opt_in:
    send_welcome(user.email, user.name)


# api/routes/admin/endpoints.py — different rule, same mechanic
send_welcome(invitee.email, invitee.name)
```

The business rule differs between the two callers; the mechanics do not. If
the template or provider changes, one file changes.

## Mental model

```
New feature? → write it in the handler first → repeated ops appear? → extract a service
                                             → no repetition?       → leave it alone
```

In one sentence: **handlers orchestrate domain rules; the service layer
centralizes reusable mechanics behind a composable, explicit-input API.**
