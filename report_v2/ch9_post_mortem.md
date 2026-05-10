# Chapter 9 — Post-Mortem

## 9.1 What Went Well

**Iterative sprint structure.** Fortnightly sprint reviews with the supervisor prevented late-stage scope divergence. Both major technical risks — the midnight boundary calculation and the audit chain reordering vulnerability — were identified and resolved within their respective sprints rather than at system integration, limiting their impact on subsequent work.

**LPM-MLED post-correction.** The decision to implement a domain-specific confusion-pair cost matrix, rather than applying a generic edit distance, was technically correct. The 8.1 percentage-point accuracy gain attributable to the correction step validated the additional implementation effort in Sprint 5.

**SQLite WAL for edge deployment.** The database engine selection proved well-suited to the deployment constraints. No schema migration issues arose during the twelve-sprint development period, and WAL mode's concurrent read behaviour eliminated any gate-write/dashboard-read contention that would have required a separate caching layer.

**Test suite completeness.** Building the 160-test non-YOLO suite incrementally — with tests written alongside implementation rather than retrospectively — meant that the Sprint 12 CDL Specialisation Layer was added without introducing regressions in the attendance or audit modules. The integration tests in particular caught two edge cases in the night-shift attribution logic that unit tests had not surfaced.

---

## 9.2 What Would Be Done Differently

**Earlier hardware procurement.** Production latency benchmarking on the Jetson Nano target platform was deferred throughout the project due to hardware availability. This leaves a gap in the NFR-01 evaluation: the 294 ms figure is known only for development hardware. Future projects of this type should prioritise acquiring production-representative hardware by Sprint 3, so that latency-sensitive design decisions (inference batch size, frame decimation rate) are grounded in real figures rather than extrapolated estimates.

**Dataset diversity from Sprint 1.** The 2,400-image dataset was collected across four lighting conditions but concentrated on vehicles registered within the past five years. Older plates with faded paint and non-standard character spacing were underrepresented. A dedicated data collection day at CDL targeting the oldest 20% of registered vehicles, scheduled at the start of the project, would have improved the classifier's robustness on degraded plates and potentially closed the 8.7% accuracy gap without requiring additional model architecture changes.

**Driver portal scoped from the outset.** The absence of a driver self-service view was identified as a limitation only after the system was complete. Had this been included as a requirements stakeholder (the employee driver, in addition to the Gate Operator, Manager, and Admin stakeholders), FR-14 could have been scoped, estimated, and either delivered or explicitly deferred with justification in Sprint 2 rather than surfacing as an omission post-delivery.

---

## 9.3 Lessons Learned

The primary lesson from this project is that domain context — CDL's shift structure, its subcontractor management model, its ISO 45001 OHS obligations — should be elicited in depth at requirements stage rather than retrofitted during implementation. The Sprint 6 scope expansion to include the CDL Specialisation Layer was the right technical decision, but it would have been more efficiently executed had the project data model been designed from the outset to accommodate multi-project vehicle attribution and subcontractor company relationships. The additional Sprint 12 migration effort required to add `zone_id` and `project_code` columns to the `access_log` table was a direct consequence of this omission.
