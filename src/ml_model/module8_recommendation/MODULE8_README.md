# Module 8 — Recommendation & Assurance Reporting

Module 8 is a deterministic consumption/reporting layer for Modules 1–7. It maps validated agent findings and Module 6 drift states into evidence-traceable, confidence-aware dry-run recommendations and a structured assurance report. It reuses existing UIR, confidence, consensus, blast-radius and remediation-ranking outputs; it does not execute remediation or create cloud clients.

Readiness starts at 100 and applies explicit severity/failure penalties. Security scoring uses severity-weighted penalties (critical 45, high 25, medium 10, low 3). Identical inputs produce ordered recommendations and canonical IDs. Any LLM wording must remain subordinate to these deterministic results; offline fallback is always the deterministic explanation.
