"""Tests for lit_platform.services.session_service multi-scene behavior."""

from unittest.mock import AsyncMock, patch

import pytest

from lit_platform.persistence.database import get_db_path
from lit_platform.runtime.db import FindingStore, SessionStore
from lit_platform.runtime.models import Finding
from lit_platform.services import session_service


class TestSessionServiceMultiScene:
    def test_create_session_persists_scene_paths(self, sample_session_state_with_db, temp_project_dir):
        state = sample_session_state_with_db
        scene1 = temp_project_dir / "chapter01.md"
        scene2 = temp_project_dir / "chapter02.md"
        scene2.write_text("Second scene", encoding="utf-8")

        state.scene_path = str(scene1)
        state.scene_paths = [str(scene1), str(scene2)]
        state.depth_mode = "quick"

        sid = session_service.create_session(state)
        row = SessionStore.get(state.db_conn, sid, project_path=state.project_path)

        assert row["scene_path"] == str(scene1)
        assert row["scene_paths"] == [str(scene1), str(scene2)]
        assert row["depth_mode"] == "quick"
        assert row["checker_model"] == row["model"]
        assert row["frontier_model"] == (row["discussion_model"] or row["model"])

    def test_session_store_create_persists_explicit_tier_models(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        sid = SessionStore.create(
            state.db_conn,
            scene_path=state.scene_path,
            scene_hash="hash",
            model="sonnet",
            discussion_model="haiku",
            depth_mode="quick",
            frontier_model="haiku",
            checker_model="sonnet",
            scene_paths=[state.scene_path],
        )

        row = SessionStore.get(state.db_conn, sid)
        assert row["depth_mode"] == "quick"
        assert row["frontier_model"] == "haiku"
        assert row["checker_model"] == "sonnet"

    def test_persist_finding_saves_scene_path(self, sample_session_state_with_db, temp_project_dir):
        state = sample_session_state_with_db
        scene1 = temp_project_dir / "chapter01.md"
        scene2 = temp_project_dir / "chapter02.md"
        scene2.write_text("Second scene", encoding="utf-8")

        finding = Finding(number=1, severity="major", lens="prose", location="P1", scene_path=str(scene1))
        state.findings = [finding]
        session_service.create_session(state)

        finding.scene_path = str(scene2)
        session_service.persist_finding(state, finding)

        stored = FindingStore.get(state.db_conn, state.session_id, 1, project_path=state.project_path)
        assert stored["scene_path"] == str(scene2)

    def test_validate_session_accepts_matching_scene_set(self, temp_project_dir):
        scene1 = str((temp_project_dir / "chapter01.md").resolve())
        scene2 = str((temp_project_dir / "chapter02.md").resolve())

        data = {
            "scene_paths": [scene1, scene2],
            "scene_hash": session_service.compute_scene_hash("combined content"),
        }

        ok, msg = session_service.validate_session(
            data,
            "combined content",
            scene1,
            scene_paths=[scene2, scene1],
        )
        assert ok is True

    def test_validate_session_rejects_different_scene_set(self, temp_project_dir):
        scene1 = str((temp_project_dir / "chapter01.md").resolve())
        scene2 = str((temp_project_dir / "chapter02.md").resolve())
        scene3 = str((temp_project_dir / "chapter03.md").resolve())

        data = {
            "scene_paths": [scene1, scene2],
            "scene_hash": session_service.compute_scene_hash("combined content"),
        }

        ok, msg = session_service.validate_session(
            data,
            "combined content",
            scene1,
            scene_paths=[scene1, scene3],
        )
        assert ok is False
        assert "different scene set" in msg.lower()


class TestSessionServicePassiveStartupReads:
    def test_passive_startup_reads_return_empty_state_without_db(self, temp_project_dir):
        assert session_service.check_active_session(temp_project_dir, passive=True) == {"exists": False}
        assert session_service.load_active_session(temp_project_dir, passive=True) is None
        assert session_service.list_sessions(temp_project_dir, passive=True) == []

    def test_passive_closed_session_reads_do_not_create_db_without_file(self, temp_project_dir):
        db_path = get_db_path(temp_project_dir)

        assert session_service.load_session_by_id(temp_project_dir, 999, passive=True) is None
        assert session_service.get_session_detail(temp_project_dir, 999, passive=True) is None
        assert db_path.exists() is False

    def test_passive_startup_reads_existing_active_session_without_connection_handle(
        self,
        sample_session_state_with_db,
    ):
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P1", status="accepted"),
            Finding(number=2, severity="minor", lens="clarity", location="P2", status="rejected"),
        ]
        session_id = session_service.create_session(state)
        state.db_conn.execute(
            "UPDATE session SET accepted_count = 0, rejected_count = 0, withdrawn_count = 0 WHERE id = ?",
            (session_id,),
        )
        state.db_conn.commit()

        active = session_service.check_active_session(state.project_path, passive=True)
        listing = session_service.list_sessions(state.project_path, passive=True)
        payload = session_service.load_active_session(state.project_path, passive=True)

        assert active["exists"] is True
        assert active["session_id"] == session_id
        assert active["total_findings"] == 2
        assert len(listing) == 1
        assert payload is not None
        assert payload["session_id"] == session_id
        assert len(payload["findings"]) == 2
        assert payload["accepted_count"] == 0
        assert payload["rejected_count"] == 0
        assert payload["withdrawn_count"] == 0
        assert "_conn" not in payload

    def test_non_passive_load_active_session_refreshes_counts_and_keeps_connection(
        self,
        sample_session_state_with_db,
    ):
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P1", status="accepted"),
            Finding(number=2, severity="minor", lens="clarity", location="P2", status="rejected"),
            Finding(number=3, severity="minor", lens="style", location="P3", status="withdrawn"),
        ]
        session_id = session_service.create_session(state)
        state.db_conn.execute(
            "UPDATE session SET accepted_count = 0, rejected_count = 0, withdrawn_count = 0 WHERE id = ?",
            (session_id,),
        )
        state.db_conn.commit()

        payload = session_service.load_active_session(state.project_path)

        assert payload is not None
        assert payload["session_id"] == session_id
        assert payload["accepted_count"] == 1
        assert payload["rejected_count"] == 1
        assert payload["withdrawn_count"] == 1
        assert "_conn" in payload
        payload["_conn"].close()

    def test_passive_closed_session_reads_use_passive_connection_without_handle(
        self,
        sample_session_state_with_db,
    ):
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P1", status="accepted"),
            Finding(number=2, severity="minor", lens="clarity", location="P2", status="rejected"),
        ]
        session_id = session_service.create_session(state)
        SessionStore.complete(state.db_conn, session_id)
        state.db_conn.close()

        with patch.object(
            session_service,
            "get_connection",
            side_effect=AssertionError("passive closed-session reads must not use get_connection"),
        ), patch.object(
            session_service,
            "get_passive_connection",
            wraps=session_service.get_passive_connection,
        ) as passive_connection:
            payload = session_service.load_session_by_id(state.project_path, session_id, passive=True)
            detail = session_service.get_session_detail(state.project_path, session_id, passive=True)

        assert passive_connection.call_count == 2
        assert payload is not None
        assert payload["session_id"] == session_id
        assert payload["status"] == "completed"
        assert len(payload["findings"]) == 2
        assert "_conn" not in payload
        assert detail is not None
        assert detail["id"] == session_id
        assert detail["status"] == "completed"
        assert len(detail["findings"]) == 2

    def test_non_passive_closed_session_load_by_id_keeps_connection_for_reopen_flow(
        self,
        sample_session_state_with_db,
    ):
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P1", status="accepted"),
            Finding(number=2, severity="minor", lens="clarity", location="P2", status="rejected"),
        ]
        session_id = session_service.create_session(state)
        SessionStore.complete(state.db_conn, session_id)

        payload = session_service.load_session_by_id(state.project_path, session_id)

        assert payload is not None
        assert payload["session_id"] == session_id
        assert payload["status"] == "completed"
        assert "_conn" in payload

        SessionStore.reopen(payload["_conn"], session_id)
        reopened = SessionStore.get(payload["_conn"], session_id)

        assert reopened is not None
        assert reopened["status"] == "active"
        payload["_conn"].close()

    def test_load_session_by_id_includes_persisted_depth_mode_for_active_session(
        self,
        sample_session_state_with_db,
    ):
        state = sample_session_state_with_db
        state.depth_mode = "quick"
        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P1", status="accepted"),
        ]
        session_id = session_service.create_session(state)

        payload = session_service.load_session_by_id(state.project_path, session_id)

        assert payload is not None
        assert payload["session_id"] == session_id
        assert payload["status"] == "active"
        assert payload.get("depth_mode") == "quick"
        payload["_conn"].close()


class TestIndexContextChangeDetection:
    def test_learning_only_change_does_not_mark_stale(self, sample_session_state):
        """LEARNING.md deltas should not trigger index stale/rerun prompts."""
        baseline = session_service.detect_index_context_changes(sample_session_state)
        assert baseline is None

        before_hash = sample_session_state.index_context_hash
        sample_session_state.learning.review_count += 1
        sample_session_state.learning.preferences.append({"description": "[prose] keep sentence fragments"})

        report = session_service.detect_index_context_changes(sample_session_state)

        assert report is None
        assert sample_session_state.index_context_stale is False
        assert sample_session_state.index_changed_files == []
        assert sample_session_state.index_context_hash != before_hash

    def test_real_index_change_still_marks_stale_and_reports_file(self, sample_session_state):
        """Non-learning index changes should keep stale detection behavior."""
        baseline = session_service.detect_index_context_changes(sample_session_state)
        assert baseline is None

        canon_path = sample_session_state.project_path / "CANON.md"
        canon_path.write_text("# Canon\n\nUpdated world rule.", encoding="utf-8")

        report = session_service.detect_index_context_changes(sample_session_state)

        assert report is not None
        assert report["stale"] is True
        assert report["changed"] is True
        assert "CANON.md" in report["changed_files"]
        assert "LEARNING.md" not in report["changed_files"]


class TestRejectionPatternAnalytics:
    def test_get_rejection_pattern_analytics_aggregates_by_lens_and_severity(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P1", status="rejected"),
            Finding(number=2, severity="major", lens="logic", location="P2", status="rejected"),
            Finding(number=3, severity="minor", lens="clarity", location="P3", status="rejected"),
            Finding(number=4, severity="minor", lens="clarity", location="P4", status="accepted"),
        ]
        session_service.create_session(state)

        rows = session_service.get_rejection_pattern_analytics(state.project_path)

        assert rows == [
            {"lens": "logic", "severity": "major", "rejection_count": 2},
            {"lens": "clarity", "severity": "minor", "rejection_count": 1},
        ]

    def test_get_rejection_pattern_analytics_applies_limit_and_date_filters(self, sample_session_state_with_db):
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P1", status="rejected"),
            Finding(number=2, severity="minor", lens="clarity", location="P2", status="rejected"),
            Finding(number=3, severity="major", lens="style", location="P3", status="rejected"),
        ]
        session_service.create_session(state)

        limited_rows = session_service.get_rejection_pattern_analytics(state.project_path, limit=1)
        assert len(limited_rows) == 1

        future_rows = session_service.get_rejection_pattern_analytics(
            state.project_path,
            start_date="9999-01-01T00:00:00",
        )
        assert future_rows == []


class TestAcceptanceRateTrendAnalytics:
    @staticmethod
    def _set_session_created_at(state, session_id: int, created_at: str) -> None:
        state.db_conn.execute(
            "UPDATE session SET created_at = ? WHERE id = ?",
            (created_at, session_id),
        )
        state.db_conn.commit()

    def test_get_acceptance_rate_trend_daily_buckets(self, sample_session_state_with_db):
        state = sample_session_state_with_db

        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P1", status="accepted"),
            Finding(number=2, severity="major", lens="logic", location="P2", status="rejected"),
            Finding(number=3, severity="minor", lens="clarity", location="P3", status="rejected"),
            Finding(number=4, severity="minor", lens="clarity", location="P4", status="withdrawn"),
        ]
        session_1 = session_service.create_session(state)
        self._set_session_created_at(state, session_1, "2026-01-01T10:00:00")

        state.findings = [
            Finding(number=1, severity="major", lens="style", location="P5", status="accepted"),
            Finding(number=2, severity="minor", lens="style", location="P6", status="accepted"),
        ]
        session_2 = session_service.create_session(state)
        self._set_session_created_at(state, session_2, "2026-01-02T10:00:00")

        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P7", status="rejected"),
        ]
        session_3 = session_service.create_session(state)
        self._set_session_created_at(state, session_3, "2026-01-03T10:00:00")

        rows = session_service.get_acceptance_rate_trend(
            state.project_path,
            bucket="daily",
            window=10,
        )

        assert rows == [
            {
                "bucket_start": "2026-01-01",
                "accepted_count": 1,
                "rejected_count": 2,
                "sample_size": 3,
                "acceptance_rate": 0.3333,
            },
            {
                "bucket_start": "2026-01-02",
                "accepted_count": 2,
                "rejected_count": 0,
                "sample_size": 2,
                "acceptance_rate": 1.0,
            },
            {
                "bucket_start": "2026-01-03",
                "accepted_count": 0,
                "rejected_count": 1,
                "sample_size": 1,
                "acceptance_rate": 0.0,
            },
        ]

    def test_get_acceptance_rate_trend_weekly_bucket_and_window(self, sample_session_state_with_db):
        state = sample_session_state_with_db

        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P1", status="accepted"),
        ]
        session_1 = session_service.create_session(state)
        self._set_session_created_at(state, session_1, "2026-01-06T10:00:00")

        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P2", status="rejected"),
        ]
        session_2 = session_service.create_session(state)
        self._set_session_created_at(state, session_2, "2026-01-07T10:00:00")

        state.findings = [
            Finding(number=1, severity="minor", lens="style", location="P3", status="accepted"),
            Finding(number=2, severity="minor", lens="style", location="P4", status="accepted"),
        ]
        session_3 = session_service.create_session(state)
        self._set_session_created_at(state, session_3, "2026-01-12T10:00:00")

        rows = session_service.get_acceptance_rate_trend(
            state.project_path,
            bucket="weekly",
            window=10,
        )
        latest_only = session_service.get_acceptance_rate_trend(
            state.project_path,
            bucket="weekly",
            window=1,
        )

        assert rows == [
            {
                "bucket_start": "2026-01-05",
                "accepted_count": 1,
                "rejected_count": 1,
                "sample_size": 2,
                "acceptance_rate": 0.5,
            },
            {
                "bucket_start": "2026-01-12",
                "accepted_count": 2,
                "rejected_count": 0,
                "sample_size": 2,
                "acceptance_rate": 1.0,
            },
        ]
        assert latest_only == [
            {
                "bucket_start": "2026-01-12",
                "accepted_count": 2,
                "rejected_count": 0,
                "sample_size": 2,
                "acceptance_rate": 1.0,
            }
        ]

    def test_get_acceptance_rate_trend_rejects_unsupported_bucket(self, sample_session_state_with_db):
        state = sample_session_state_with_db

        with pytest.raises(ValueError, match="Unsupported bucket"):
            session_service.get_acceptance_rate_trend(state.project_path, bucket="hourly")


class TestSceneFindingHistory:
    def test_get_scene_finding_history_returns_newest_first_across_sessions(self, sample_session_state_with_db, temp_project_dir):
        state = sample_session_state_with_db
        scene = temp_project_dir / "chapter01.md"
        other_scene = temp_project_dir / "chapter02.md"
        other_scene.write_text("Other scene", encoding="utf-8")

        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P1", scene_path=str(scene), status="accepted"),
            Finding(number=2, severity="minor", lens="clarity", location="P2", scene_path=str(other_scene), status="rejected"),
        ]
        first_session_id = session_service.create_session(state)
        SessionStore.complete(state.db_conn, first_session_id)

        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P3", scene_path=str(scene), status="rejected"),
        ]
        second_session_id = session_service.create_session(state)
        SessionStore.complete(state.db_conn, second_session_id)

        rows = session_service.get_scene_finding_history(state.project_path, scene_id=str(scene))

        assert [row["session_id"] for row in rows] == [second_session_id, first_session_id]
        assert all(row["scene_path"] == str(scene) for row in rows)

    def test_get_scene_finding_history_applies_limit_and_offset(self, sample_session_state_with_db, temp_project_dir):
        state = sample_session_state_with_db
        scene = temp_project_dir / "chapter01.md"

        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P1", scene_path=str(scene), status="accepted"),
        ]
        first_session_id = session_service.create_session(state)
        SessionStore.complete(state.db_conn, first_session_id)

        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P2", scene_path=str(scene), status="rejected"),
        ]
        second_session_id = session_service.create_session(state)
        SessionStore.complete(state.db_conn, second_session_id)

        latest_only = session_service.get_scene_finding_history(
            state.project_path,
            scene_id=str(scene),
            limit=1,
            offset=0,
        )
        older_only = session_service.get_scene_finding_history(
            state.project_path,
            scene_id=str(scene),
            limit=1,
            offset=1,
        )

        assert len(latest_only) == 1
        assert len(older_only) == 1
        assert latest_only[0]["session_id"] == second_session_id
        assert older_only[0]["session_id"] == first_session_id


class TestFindingIndexContext:
    def test_get_finding_index_context_for_session_returns_matches(
        self,
        sample_session_state_with_db,
        temp_project_dir,
    ):
        state = sample_session_state_with_db
        (temp_project_dir / "CAST.md").write_text(
            "# CAST\n\n## Supporting Characters\n\n### Alice\n- **Role:** Warden\n",
            encoding="utf-8",
        )
        (temp_project_dir / "GLOSSARY.md").write_text(
            "# GLOSSARY\n\n## Terms\n\n### Breach Gate\n**Definition:** Portal\n",
            encoding="utf-8",
        )

        state.findings = [
            Finding(
                number=1,
                severity="major",
                lens="logic",
                location="Alice at gate",
                evidence="Alice enters the Breach Gate.",
                impact="Breach Gate remains unstable.",
                options=["Ask Alice to re-check sequence."],
                scene_path=str(temp_project_dir / "chapter01.md"),
            )
        ]
        session_id = session_service.create_session(state)

        report = session_service.get_finding_index_context_for_session(
            state.project_path,
            session_id,
            1,
        )

        assert report["summary"]["match_count"] == 2
        assert [row["entry"] for row in report["rows"]] == ["Alice", "Breach Gate"]

    def test_get_finding_index_context_for_session_missing_finding_returns_empty(
        self,
        sample_session_state_with_db,
    ):
        state = sample_session_state_with_db
        session_id = session_service.create_session(state)

        report = session_service.get_finding_index_context_for_session(
            state.project_path,
            session_id,
            999,
            scopes=["glossary"],
            max_matches_per_scope=2,
        )

        assert report["filters"]["scopes"] == ["glossary"]
        assert report["filters"]["max_matches_per_scope"] == 2
        assert report["summary"]["match_count"] == 0
        assert report["rows"] == []

class TestReevaluationCheckerModelRouting:
    @pytest.mark.asyncio
    async def test_detect_scene_changes_prefers_effective_checker_model_id(
        self,
        sample_session_state_with_db,
    ):
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="logic", location="P1", stale=True)
        ]
        state.effective_checker_model_id = "checker-model-id-override"

        with patch(
            "lit_platform.services.session_service.apply_scene_change",
            return_value={"adjusted": 0, "stale": 1, "no_lines": 0},
        ), patch(
            "lit_platform.runtime.api.re_evaluate_finding",
            new=AsyncMock(return_value={"finding_number": 1}),
        ) as mock_re_eval:
            scene_path = state.project_path / "chapter01.md"
            scene_path.write_text("Changed scene content", encoding="utf-8")

            report = await session_service.detect_and_apply_scene_changes(state, current_index=0)

        assert report is not None
        assert report["changed"] is True
        assert len(report["re_evaluated"]) == 1
        assert mock_re_eval.await_count == 1
        assert mock_re_eval.await_args.kwargs["model"] == "checker-model-id-override"

    @pytest.mark.asyncio
    async def test_review_current_finding_prefers_effective_checker_model_id(
        self,
        sample_session_state_with_db,
    ):
        state = sample_session_state_with_db
        state.findings = [
            Finding(number=1, severity="major", lens="clarity", location="P1", stale=False)
        ]
        state.effective_checker_model_id = "checker-model-id-override"

        with patch(
            "lit_platform.services.session_service.apply_scene_change",
            return_value={"adjusted": 0, "stale": 0, "no_lines": 0},
        ), patch(
            "lit_platform.runtime.api.re_evaluate_finding",
            new=AsyncMock(return_value={"finding_number": 1}),
        ) as mock_re_eval:
            scene_path = state.project_path / "chapter01.md"
            scene_path.write_text("Changed scene content again", encoding="utf-8")

            report = await session_service.review_current_finding_against_scene_edits(state, current_index=0)

        assert report["changed"] is True
        assert len(report["re_evaluated"]) == 1
        assert mock_re_eval.await_count == 1
        assert mock_re_eval.await_args.kwargs["model"] == "checker-model-id-override"
