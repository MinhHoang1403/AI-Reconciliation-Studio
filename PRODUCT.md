# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React + TypeScript + Vite, served by Nginx; backend FastAPI + Polars + PostgreSQL (see `docs/ARCHITECTURE.md`). Chosen by Owner when approving the architecture.

## Users

- Anyone who must reconcile business data — shop owners, accountants, operations staff — including people who do not know reconciliation practice. They upload their files and talk to an AI Assistant instead of configuring rules.
- The same demo is also shown to evaluators (lecturers, recruiters, managers), who must see clearly what the AI does and why the results can be trusted.

## Product Purpose

AI Reconciliation Studio turns raw exports (orders, payments, bank statements) into a reconciled result: upload → chat with the Assistant → receive matches, mismatches, KPIs, charts and a report. It automates the simple cases and stops only at cells or rows it cannot decide, pointing to them with an AI-suggested fix for the user to confirm. Success: a non-expert finishes a reconciliation and trusts the result.

## Positioning

AI suggests, deterministic code decides. Every number and every matched pair comes from a reproducible engine with stated reasons and a trace back to the original row; Gemini only interprets columns, understands chat, and explains. Results are checked by an independent validator before any report uses them.

## Operating Context

- Inputs: CSV and XLSX exports up to at least 100,000 rows; Vietnamese bank statements where the order code sits inside the transfer description.
- First domain: sales (orders ↔ payments ↔ bank statement).
- Single user, local deployment on `127.0.0.1`; demo, not production.
- Assistant traces are reviewed in a local Langfuse instance.

## Capabilities and Constraints

- Flow: read → column mapping → normalization → error handling → clean dataset → choose reconciliation fields → reconcile → validate → report.
- Confidence tiers: high = do automatically and log; medium = suggest, confirm once per group; low = stop at the exact cell and ask.
- Changes the Assistant wants to make appear as confirmation cards in the chat.
- Raw uploads are never modified; every step creates a new version.
- Out of scope for the demo: PDF/Docs input, PDF export, N:N matching, multi-user.

## Brand Commitments

Name: **AI Reconciliation Studio**. No logo or palette committed yet.

## Evidence on Hand

No real customer data, testimonials or benchmarks. Demo data will be synthetic fixtures with an answer key (`tests/fixtures/sales/`); do not present invented metrics or customers.

## Product Principles

1. Trust is the product: every result shows its reason and its source row.
2. Ask only where it matters: automate the clear cases, surface the unclear ones precisely.
3. Conversation first, screens as evidence: the chat drives the flow, the pages show and verify the data.
4. Understandable without domain knowledge: plain Vietnamese, technical terms explained.

## Accessibility & Inclusion

- Interface language: Vietnamese only, including all Assistant replies.
- Must work well on both desktop and phone; data tables need a usable mobile presentation, not just horizontal overflow.
