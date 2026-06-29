# ADR 0001: Deliberation ontology (IBIS/QOC backbone)

- Status: accepted
- Date: 2026-06-29

## Context

FatCat extracts durable knowledge about the user from conversations. The flat
`Issue` type conflated two genuinely different things:

- a meta knowledge gap FatCat wants to learn about the *user*
  (e.g. "Under which conditions does the user prefer relational databases?"), and
- a concrete decision the *user* actually faced in their work
  (e.g. "Which database should this project use?").

Collapsing both into one "issue" caused drift: project decisions leaked into the
user model, and user-learning questions were phrased as project tasks. We also
lacked a place to record *why* a decision was made (positions, criteria,
arguments) — the bridge from a single project decision to a durable user
preference.

## Decision

Adopt an explicit deliberation ontology with IBIS/QOC as the curated semantic
backbone:

```text
Inquiry
├── LearningQuestion      # what FatCat wants to learn about the user
│   ├── Hypotheses        # tentative answers being tested
│   └── user evidence
└── DecisionIssue         # an IBIS issue the user deliberated
    ├── Positions         # candidate answers / options
    ├── Criteria          # QOC criteria used to judge positions
    └── Arguments         # supports/opposes, optionally via a criterion
```

Principles:

1. **IBIS/QOC is the authoritative, user-curated backbone.** `DecisionIssue`,
   `Position`, `Criterion`, and `Argument` are first-class, reviewable objects.
2. **Dialogue acts and discourse relations are non-authoritative evidence
   annotations.** They are derived observations attached to evidence, never
   memories, and never direct storage rules. A single utterance can be a
   preference, a decision, and a rationale at once, so dialogue acts are
   multi-label. Interpretation strength is computed from explicitness,
   repetition, confirmation/correction, temporal stability, cross-project
   recurrence, scope, and interpretation certainty — not from the act label.
3. **Design rationale is a derived view,** projected from the curated graph
   (issue, current/adopted position, decision status, criteria, supporting and
   conflicting arguments, evidence, timeline). It needs no own extractor.
4. **Criteria are the bridge** from a single project decision to the durable
   user model (e.g. "Use FastAPI because I value type safety" yields the
   criteria *type safety* and *low boilerplate*, which may seed a
   `LearningQuestion` about the user's standing preference).
5. **Themes are synthesized slowly,** only from confirmed evidence across
   multiple reviewed sessions; never from a single message. Keyword (lexical),
   topic (subject area), and theme (interpretive pattern) stay distinct.

## Status values

- `DecisionIssue.status`: `open`, `exploring`, `tentative`, `adopted`,
  `superseded`.
- `Position.status`: `proposed`, `tentative`, `adopted`, `rejected`,
  `superseded`.
- `Argument.stance`: `supports`, `opposes`.
- `Hypothesis.status`: `open`, `supported`, `refuted`, `confirmed`.

## Scope of the first step (this change)

Domain-first only: introduce the types, candidate variants, and minimal
lifecycle policies with tests. No extraction, persistence, or CLI wiring yet.
The existing `Issue`/`IssueCandidate` become `LearningQuestion`/
`LearningQuestionCandidate`; the old names remain as backward-compatible
aliases and the stored `item_type` values are unchanged.

## Consequences

- Clear separation prevents project decisions from polluting the user model.
- A later session-level synthesis step can populate both branches and be
  reviewed as one cluster rather than per clause.
- Subsequent steps (dialogue acts, discourse relations, session synthesis,
  rationale view, themes) attach to this backbone without reshaping it.
