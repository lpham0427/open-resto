# 1. Record architecture decisions

Date: 2026-10-04

## Status

Accepted

## Context

We need to record the architectural decisions made on this project so that
current and future contributors can understand why the system is shaped the
way it is.

## Decision

We will use Architecture Decision Records (ADRs), as described by Michael
Nygard in
[Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

ADRs are stored in `docs/adr/` as Markdown files named
`NNNN-short-title.md`, numbered sequentially. Each ADR has the sections
Status, Context, Decision and Consequences.

## Consequences

- Significant decisions are documented together with their context and
  trade-offs.
- New contributors can read the history of decisions instead of guessing.
- Superseded decisions are kept and marked as superseded, not deleted.
- Writing an ADR adds a small amount of overhead to each significant decision.
