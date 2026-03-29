# Roadmap

This roadmap reflects **personal priorities** based on my novel-writing needs. Features will be implemented as I need them for my own work. No timeline or guarantees.

---

## Cross-session analytics

1. **Rejection pattern report** — "Across my last N sessions, which lens/severity combinations do I reject most?" Query finding rows by `status='rejected'` grouped by lens and severity. Surface whether the learning system has captured these patterns, or if there are gaps.

2. **Per-scene finding history** — "What were the findings for scene `01.02.03` across all sessions?" Currently you can view findings per session, but not query findings by scene path across sessions. Useful for tracking whether re-reviews of the same scene improve.

3. **Acceptance rate trend** — "Am I accepting more findings over time as the learning system adapts?" A simple time-series query across sessions showing accepted/rejected/withdrawn ratios. Helps gauge whether learning is working.

4. **Recurring issue detector** — "Are the same locations/evidence patterns appearing in multiple sessions?" Cross-reference findings across sessions to flag issues that keep resurfacing despite being accepted (author agrees but doesn't fix).

---

## Finding-to-knowledge cross-referencing (during review)

5. **Relevant knowledge context on findings** — When a finding references a continuity or logic issue, automatically surface the specific CANON/extracted Cast/Timeline entries it relates to. Currently the author must mentally cross-reference. This could be a "show context" action during finding review.

6. **Knowledge coverage gap report** — "Which characters / terms / threads haven't appeared in any reviewed scene?" Cross-reference extracted knowledge entries against scenes that have been analyzed. Useful for spotting world-building elements that are defined but never used.

7. **Finding-driven knowledge suggestions** — When a finding is accepted (author agrees there's a problem), suggest specific CANON.md or knowledge corrections that would prevent the issue in future scenes.

---

## Arc-level workflow (beyond single session)

8. **Chapter/arc summary** — After reviewing a sequence of scenes (across multiple sessions), generate a synthesis: common themes, unresolved threads, editorial patterns. Goes beyond the single-session disconfirming summary to provide manuscript-level editorial intelligence.

9. **Thread tracker** — Cross-reference extracted thread entries against findings and reviewed scenes: which threads have been flagged, which have been addressed, which are still open. A dashboard-level view of narrative promise health.

---

## Pre-analysis efficiency

10. **Deterministic code checks** — ✅ Delivered. Deterministic validations run automatically as Phase 1 of every `quick`/`deep` analysis session (no separate mode needed).
