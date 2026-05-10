# Chapter 8 — End-Project Report

## 8.1 Project Objectives vs. Deliverables

The project was scoped through a Project Initiation Document (PID) submitted at the outset of PUSL3190. The PID proposed an ALPR-based attendance system with a Multi-Gate Spatial Verification fraud detection layer. As described in §5.1, the spatial verification component was formally descoped at the Sprint 6 review on the direction of the project supervisor, who determined that fraud detection added unnecessary complexity beyond the core attendance requirement. All remaining PID objectives were delivered.

The primary deliverable — a shift-aware vehicle attendance system with a SHA-256 tamper-evident audit chain and a CDL-contextualised analytics layer — was completed across thirteen two-week sprints (October 2025 to April 2026). The system was delivered as a single-repository Python application deployable on CDL's gate-side edge hardware without external network dependencies.

---

## 8.2 Scope Changes

One formal scope change was approved during the project:

- **Sprint 6 — Multi-Gate Spatial Verification descoped.** The original PID included a second camera at CDL's exit gate and a transit-time anomaly detector. The supervisor directed that the core attendance problem should be solved first; fraud detection was reframed as a future enhancement. The vacated sprint capacity was reallocated to the CDL Specialisation Layer (drydock zones, project attribution, subcontractor billing audit), which was agreed at the Sprint 6 review as a higher-priority deliverable that more authentically reflected CDL's operational analytics needs.

---

## 8.3 Limitations and Future Work

The primary hardware limitation — the production Jetson Nano latency gap — is discussed in §7.2. Two additional enhancements are identified for future development:

- **Driver self-service portal.** A read-only web view, authenticated by employee number and registered plate, would allow CDL employees to verify their own attendance and fuel allowance accrual without raising HR tickets. This directly reduces the 20-hours-per-month administrative burden identified in CDL Finance's 2023 internal audit.

- **Multi-site topology.** Migrating the data layer from SQLite to a client-server engine would allow VAAS to serve CDL's subsidiary facilities (DGES, DTS) from a unified analytics dashboard. The application architecture supports this transition; only the database driver and connection management layer would require modification.

---

## 8.4 Reflection on Process

The iterative Agile approach with fortnightly supervisor reviews was effective in surfacing scope ambiguities early. The two most significant technical challenges — the midnight boundary handling in the attendance engine and the row-reordering attack vector in the audit chain — were both identified during review cycles (Sprint 5 integration testing and Sprint 10 security review respectively) rather than at final evaluation. This confirms the value of structured interim checkpoints in a solo development project where there is no peer code review process.

The decision to use SQLite WAL rather than a traditional RDBMS was validated by the load test results: eight concurrent sessions with MJPEG streaming and SSE event feeds produced stable CPU and memory utilisation. For the single-site CDL deployment, this choice eliminated significant operational complexity without any measurable performance penalty.
