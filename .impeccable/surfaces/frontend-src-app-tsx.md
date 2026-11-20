---
version: 1
slug: "frontend-src-app-tsx"
primary_target: "frontend/src/App.tsx"
related_targets: []
---

# App shell — Tổng quan, Assistant, Dữ liệu, Đối soát, Báo cáo

Scope: the whole web app shell; mode Operate. First screen is Tổng quan (overview). Assistant is a full page plus reachable from every page. Vietnamese only; desktop and phone both first-class.

Audience/job: non-expert shop owners and accountants reconcile orders, payments, bank statements; evaluators watch what the AI did. Avoid: ChatGPT-clone empty chat, dense old accounting software, effect-heavy styling.

## Direction contract

THESIS: Results are printed with the discipline of a Vietnamese polymer banknote — denomination colour as meaning, fine guilloche only where authenticity is proven. Refuses the indigo-SaaS KPI-card dashboard.

OWN-WORLD: cool polymer-white ground (#f2f5f4), deep 500.000đ teal shell rail (#0f4c55), 200.000đ orange-red for needs-attention (#c4552f), 100.000đ green for matched (#3f7a3b), ink #13252a; every tint derived from these, no free greys. Be Vietnam Pro, tabular numerals at banknote-denomination scale. One reserved hue for the step in progress.

STORY: the visitor sees the single next decision, how much data each source holds, and whether the last run's result is verified; they act on the decision or ask the Assistant.

FIRST VIEWPORT: teal rail left (nav: Tổng quan, Assistant, Dữ liệu, Đối soát, Báo cáo); main column: page title, next-decision band with a large denomination-scale count and primary action; below, last-run result counts and dataset list with row-count bars; right column the verification seal. Phone: rail becomes bottom tab bar, seal drops below results.

FORM: candidate 3 of 7 (Tiền polymer), seed:a6d97c50649f75f0. Signature move: the verification seal is a guilloche rosette drawn from the run's validation checks; a failed check breaks the rosette ring it belongs to. Raises: two-value palette discipline (Ikeda); reserved active-step hue (orienteering); size encodes extent (acetate manual); every figure carries its source reference (design annual).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
