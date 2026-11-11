# ADR 0004: Use AI for triage drafts and verify every quote against the evidence

- **Status:** Accepted
- **Date:** 2026-11-11

## Context
Diagnosis is slow and inconsistent when engineers collect different evidence each time. A language
model can read events and logs quickly, but it can also state a cause that the evidence does not show.

## Decision
`aos-ops triage` collects the same read-only evidence every time, removes secrets from it, and only
sends it to the Claude API when `--send` is given. The model must answer in a fixed schema and quote
each piece of evidence exactly, with the id of the item it came from. The tool then checks each quote:
`verified`, `wrong_source` (right text, other item) or `not_found`. A draft with an unverifiable
quote is marked "do not trust". The answer is a draft for an incident note; an engineer verifies it.

## Alternatives considered
- **No AI, playbook only:** reliable, but slow for faults that are not in the playbook.
- **Trust the model's answer as written:** fast, but a confident wrong cause wastes time in an incident.
- **Send raw logs:** simpler, but secrets could leave the computer; cleaning comes first.

## Consequences
- Every claim in a draft can be traced to a line in the evidence.
- Evidence, not the model's reasoning, is what the engineer checks.
- Triage depends on an external API and an API key, and costs tokens; a dry run prints the estimate first.
