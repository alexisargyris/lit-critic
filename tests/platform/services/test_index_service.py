"""
Unit tests for lit_platform.services.index_service.

Tests are designed to run without a live LLM connection.  LLM calls are
mocked via unittest.mock so the logic of insertion, dedup-detection,
reconciliation, and report formatting can be exercised independently.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from lit_platform.services.index_service import (
    # Duplicate detection
    _already_exists,
    # Reconciliation helpers
    _extract_existing_entry,
    _extract_inline_value,
    _is_placeholder,
    _item_key_prefix,
    _merge_field_block,
    _merge_sub_items,
    _parse_entry_into_blocks,
    _reconcile_entries,
    _replace_entry_in_content,
    # Insertion helpers
    _insert_into_section,
    # Public API
    format_report,
    get_finding_index_context,
    get_index_coverage_gaps,
    scan_scene_for_index_entries,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CAST_ENTRY_ALICE = """\
### Alice
- **Age:** 24
- **Role:** Sanctuary warden
- **Physical:** 168cm, lean build
- **Key facts:**
  - First seen: 01.01.01
  - Only survivor of her squad
- **Relationships:**
  - George: mentor, trusts implicitly
  - Lyra: complicated loyalty"""

CAST_ENTRY_ALICE_NEW = """\
### Alice
- **Age:** 24 (born Year 818 PA)
- **Role:** Sanctuary warden, former soldier
- **Physical:** [TODO]
- **Key facts:**
  - First seen: 01.02.01
  - Received a blood transfusion from Lyra
- **Relationships:**
  - George: mentor, trusts implicitly
  - Lyra: now owes a debt"""

GLOSSARY_ENTRY_BREACH = """\
### Breach Gates
**Definition:** The ancient sealed portals leading to the underworld.
**First seen:** 01.01.03
**Notes:** Always capitalized."""

GLOSSARY_ENTRY_BREACH_NEW = """\
### Breach Gates
**Definition:** The ancient sealed portals leading to the underworld. Locked 200 years ago.
**First seen:** 01.03.01
**Notes:** [TODO]"""

THREAD_ENTRY_VAULT = """\
### vault_mystery
**Opened:** 01.01.02
**Question:** What is inside the vault?
**Status:** Active.
**Notes:** [TODO]"""

THREAD_ENTRY_VAULT_NEW = """\
### vault_mystery
**Opened:** 01.03.01
**Question:** What is inside the vault? Who sealed it?
**Status:** Active. Vault door found ajar.
**Notes:** Connected to ward collapse."""


# ---------------------------------------------------------------------------
# _already_exists
# ---------------------------------------------------------------------------

class TestAlreadyExists:
    def test_exact_heading_match(self):
        content = "### Alice\n\nA character.\n"
        assert _already_exists("Alice", content) is True

    def test_case_insensitive_match(self):
        content = "### alice\n\nA character.\n"
        assert _already_exists("Alice", content) is True

    def test_not_present(self):
        content = "### Bob\n\nA character.\n"
        assert _already_exists("Alice", content) is False

    def test_partial_word_not_a_match(self):
        # "Ali" should NOT match "### Alice"
        content = "### Alice\n"
        assert _already_exists("Ali", content) is False

    def test_scene_id_match(self):
        content = "**01.03.01** Amelia descends.\n"
        assert _already_exists("01.03.01", content) is True

    def test_thread_id_match(self):
        content = "### vault_mystery\n**Opened:** 01.01.02\n"
        assert _already_exists("vault_mystery", content) is True


# ---------------------------------------------------------------------------
# _extract_existing_entry
# ---------------------------------------------------------------------------

class TestExtractExistingEntry:
    def test_extracts_entry_between_headings(self):
        content = "# CAST\n\n### Alice\n- **Age:** 24\n\n### Bob\n- **Age:** 30\n"
        result = _extract_existing_entry(content, "Alice")
        assert result == "### Alice\n- **Age:** 24"
        assert "Bob" not in result

    def test_extracts_last_entry_in_file(self):
        content = "# CAST\n\n### Alice\n- **Age:** 24\n"
        result = _extract_existing_entry(content, "Alice")
        assert result == "### Alice\n- **Age:** 24"

    def test_returns_empty_when_not_found(self):
        content = "### Bob\n- **Age:** 30\n"
        result = _extract_existing_entry(content, "Alice")
        assert result == ""

    def test_strips_auto_marker_for_comparison(self):
        content = "### Alice  <!-- ⚡ auto: 01.01.01 -->\n- **Age:** 24\n\n### Bob\n"
        result = _extract_existing_entry(content, "Alice")
        assert "<!-- ⚡ auto:" in result  # marker preserved in extracted text
        assert "Bob" not in result

    def test_case_insensitive_lookup(self):
        content = "### alice\n- **Age:** 24\n"
        result = _extract_existing_entry(content, "Alice")
        assert result.startswith("### alice")

    def test_extracts_timeline_entry(self):
        content = "## Part 01\n\n### Chapter 01\n\n**01.01.01** Amelia wakes.\n\n**01.01.02** Amelia searches.\n"
        result = _extract_existing_entry(content, "01.01.01")
        assert "**01.01.01** Amelia wakes." in result
        assert "01.01.02" not in result

    def test_extracts_entry_preceded_by_section_heading(self):
        content = (
            "## Supporting Characters\n\n"
            "### Alice\n- **Age:** 24\n\n"
            "## Minor Characters\n\n"
            "### Guard\n- **Role:** Guard\n"
        )
        result = _extract_existing_entry(content, "Alice")
        assert result == "### Alice\n- **Age:** 24"

    def test_no_trailing_blank_lines_in_result(self):
        content = "### Alice\n- **Age:** 24\n\n\n### Bob\n"
        result = _extract_existing_entry(content, "Alice")
        assert not result.endswith("\n")


# ---------------------------------------------------------------------------
# _parse_entry_into_blocks
# ---------------------------------------------------------------------------

class TestParseEntryIntoBlocks:
    def test_cast_entry_parsed_correctly(self):
        heading, preamble, blocks = _parse_entry_into_blocks(CAST_ENTRY_ALICE)
        assert heading == "### Alice"
        assert preamble == []
        assert "age" in blocks
        assert "role" in blocks
        assert "physical" in blocks
        assert "key facts" in blocks
        assert "relationships" in blocks

    def test_field_values_captured(self):
        _, _, blocks = _parse_entry_into_blocks(CAST_ENTRY_ALICE)
        age_header = blocks["age"][0]
        assert "24" in age_header

    def test_sub_items_captured(self):
        _, _, blocks = _parse_entry_into_blocks(CAST_ENTRY_ALICE)
        key_facts_block = blocks["key facts"]
        assert any("First seen" in ln for ln in key_facts_block)
        assert any("Only survivor" in ln for ln in key_facts_block)

    def test_glossary_entry_parsed(self):
        heading, preamble, blocks = _parse_entry_into_blocks(GLOSSARY_ENTRY_BREACH)
        assert heading == "### Breach Gates"
        assert "definition" in blocks
        assert "first seen" in blocks
        assert "notes" in blocks

    def test_thread_entry_parsed(self):
        heading, _, blocks = _parse_entry_into_blocks(THREAD_ENTRY_VAULT)
        assert heading == "### vault_mystery"
        assert "opened" in blocks
        assert "question" in blocks
        assert "status" in blocks

    def test_preamble_captured(self):
        entry = "### Alice\nA brave warrior.\n- **Age:** 24\n"
        heading, preamble, blocks = _parse_entry_into_blocks(entry)
        assert heading == "### Alice"
        assert any("A brave warrior." in ln for ln in preamble)
        assert "age" in blocks

    def test_single_line_entry_no_blocks(self):
        entry = "**01.01.01** Amelia wakes in the sanctuary."
        heading, preamble, blocks = _parse_entry_into_blocks(entry)
        assert heading == "**01.01.01** Amelia wakes in the sanctuary."
        assert preamble == []
        assert blocks == {}


# ---------------------------------------------------------------------------
# _is_placeholder / _extract_inline_value / _item_key_prefix
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_is_placeholder_todo(self):
        assert _is_placeholder("[TODO]") is True

    def test_is_placeholder_todo_with_note(self):
        assert _is_placeholder("[TODO — fill in details]") is True

    def test_is_placeholder_empty(self):
        assert _is_placeholder("") is True

    def test_is_placeholder_real_value(self):
        assert _is_placeholder("24") is False
        assert _is_placeholder("Sanctuary warden") is False

    def test_extract_inline_value_dash_style(self):
        assert _extract_inline_value("- **Age:** 24") == "24"

    def test_extract_inline_value_no_dash(self):
        assert _extract_inline_value("**Definition:** Some text here") == "Some text here"

    def test_extract_inline_value_no_match(self):
        assert _extract_inline_value("  - First seen: 01.01.01") == ""

    def test_item_key_prefix_relationship(self):
        assert _item_key_prefix("  - George: mentor, father-figure") == "george"

    def test_item_key_prefix_two_word_name(self):
        assert _item_key_prefix("  - Lyra Voss: complicated loyalty") == "lyra voss"

    def test_item_key_prefix_no_colon(self):
        assert _item_key_prefix("  - Fought in the war") is None

    def test_item_key_prefix_long_candidate(self):
        # Long prefix should not be treated as a key
        line = "  - This is a very long key that should not match: value"
        assert _item_key_prefix(line) is None


# ---------------------------------------------------------------------------
# _merge_sub_items
# ---------------------------------------------------------------------------

class TestMergeSubItems:
    def test_new_items_come_first(self):
        old = ["  - George: mentor"]
        new = ["  - George: now distrusted"]
        result = _merge_sub_items(old, new)
        assert any("now distrusted" in ln for ln in result)
        assert not any("mentor" in ln for ln in result)  # old "George" replaced

    def test_unique_old_item_preserved(self):
        old = ["  - George: mentor", "  - Only survivor of her squad"]
        new = ["  - George: now distrusted", "  - Received a transfusion"]
        result = _merge_sub_items(old, new)
        assert any("Only survivor" in ln for ln in result)
        assert any("Received a transfusion" in ln for ln in result)
        assert any("now distrusted" in ln for ln in result)

    def test_exact_duplicate_not_repeated(self):
        line = "  - Trained by George since age 13"
        result = _merge_sub_items([line], [line])
        assert result.count(line) == 1

    def test_todo_items_filtered_out(self):
        old = ["  - [TODO]"]
        new = ["  - Real fact about character"]
        result = _merge_sub_items(old, new)
        assert not any("[TODO]" in ln for ln in result)
        assert any("Real fact" in ln for ln in result)

    def test_fallback_when_both_empty(self):
        old = ["  - [TODO]"]
        new = []
        result = _merge_sub_items(old, new)
        # Fallback: return old when result would be empty
        assert result == old


# ---------------------------------------------------------------------------
# _merge_field_block
# ---------------------------------------------------------------------------

class TestMergeFieldBlock:
    def test_new_wins_on_real_conflict(self):
        old = ["- **Role:** Warden"]
        new = ["- **Role:** Warden, former soldier"]
        result = _merge_field_block(old, new)
        assert "former soldier" in result[0]

    def test_old_wins_when_new_is_placeholder(self):
        old = ["- **Physical:** 168cm, lean build"]
        new = ["- **Physical:** [TODO]"]
        result = _merge_field_block(old, new)
        assert "168cm" in result[0]

    def test_new_wins_when_old_is_placeholder(self):
        old = ["- **Age:** [TODO]"]
        new = ["- **Age:** 24"]
        result = _merge_field_block(old, new)
        assert "24" in result[0]

    def test_immutable_opened_field_always_keeps_old(self):
        old = ["**Opened:** 01.01.02"]
        new = ["**Opened:** 01.03.01"]
        result = _merge_field_block(old, new, field_key="opened")
        assert "01.01.02" in result[0]
        assert "01.03.01" not in result[0]

    def test_immutable_first_seen_always_keeps_old(self):
        old = ["**First seen:** 01.01.01"]
        new = ["**First seen:** 01.05.03"]
        result = _merge_field_block(old, new, field_key="first seen")
        assert "01.01.01" in result[0]

    def test_list_field_merges_sub_items(self):
        old = ["- **Key facts:**", "  - First seen: 01.01.01", "  - Only survivor"]
        new = ["- **Key facts:**", "  - First seen: 01.02.01", "  - Received a transfusion"]
        result = _merge_field_block(old, new, field_key="key facts")
        combined = "\n".join(result)
        # "First seen" is NOT a 2-word key with len < 30 — it won't deduplicate
        assert "Only survivor" in combined
        assert "Received a transfusion" in combined


# ---------------------------------------------------------------------------
# _reconcile_entries
# ---------------------------------------------------------------------------

class TestReconcileEntries:
    def test_new_fills_todo_fields(self):
        old = "### Alice\n- **Age:** [TODO]\n- **Role:** Warden\n"
        new = "### Alice\n- **Age:** 24\n- **Role:** [TODO]\n"
        result = _reconcile_entries(old, new)
        assert "- **Age:** 24" in result
        assert "- **Role:** Warden" in result

    def test_old_unique_fields_preserved(self):
        old = CAST_ENTRY_ALICE
        new = "### Alice\n- **Age:** 24 (born Year 818 PA)\n- **Role:** Former soldier\n"
        result = _reconcile_entries(old, new)
        # Fields from old entry that are not in new entry must be present
        assert "Physical" in result
        assert "Key facts" in result
        assert "Relationships" in result

    def test_new_unique_fields_added(self):
        old = "### Alice\n- **Age:** 24\n"
        new = "### Alice\n- **Age:** 24\n- **Role:** Warden\n"
        result = _reconcile_entries(old, new)
        assert "Role" in result

    def test_heading_kept_from_old(self):
        old = "### Alice  <!-- ⚡ auto: 01.01.01 -->\n- **Age:** 24\n"
        new = "### Alice\n- **Age:** 25\n"
        result = _reconcile_entries(old, new)
        # Old heading (with auto-marker) is preserved
        assert "<!-- ⚡ auto: 01.01.01 -->" in result

    def test_relationships_merged(self):
        old = "### Alice\n- **Relationships:**\n  - George: mentor\n  - Lyra: friend\n"
        new = "### Alice\n- **Relationships:**\n  - George: now distrusted\n  - Bob: new ally\n"
        result = _reconcile_entries(old, new)
        assert "now distrusted" in result
        assert "Lyra: friend" in result  # unique to old
        assert "Bob: new ally" in result  # unique to new
        # Old George description replaced by new
        assert "mentor" not in result

    def test_opened_field_immutable(self):
        result = _reconcile_entries(THREAD_ENTRY_VAULT, THREAD_ENTRY_VAULT_NEW)
        # "Opened" should keep the old value
        assert "01.01.02" in result
        assert "01.03.01" not in result.split("**Opened:**")[1].split("\n")[0]

    def test_first_seen_immutable_in_glossary(self):
        result = _reconcile_entries(GLOSSARY_ENTRY_BREACH, GLOSSARY_ENTRY_BREACH_NEW)
        # "First seen" should keep old value 01.01.03, not 01.03.01
        assert "01.01.03" in result

    def test_notes_field_new_wins_when_old_is_todo(self):
        old = "### Breach Gates\n**Definition:** Old def.\n**Notes:** [TODO]\n"
        new = "### Breach Gates\n**Definition:** New def.\n**Notes:** Detailed notes.\n"
        result = _reconcile_entries(old, new)
        assert "Detailed notes." in result

    def test_notes_field_old_wins_when_new_is_todo(self):
        old = "### Breach Gates\n**Definition:** Old def.\n**Notes:** Always capitalized.\n"
        new = "### Breach Gates\n**Definition:** New def.\n**Notes:** [TODO]\n"
        result = _reconcile_entries(old, new)
        assert "Always capitalized." in result

    def test_preamble_preserved_from_old(self):
        old = "### Alice\nA brave warrior with unknown origins.\n- **Age:** 24\n"
        new = "### Alice\n- **Age:** 24\n- **Role:** Warden\n"
        result = _reconcile_entries(old, new)
        assert "A brave warrior with unknown origins." in result
        assert "Role" in result  # new field added

    def test_timeline_single_line_new_wins(self):
        old = "**01.01.01** [TODO — outcome summary]"
        new = "**01.01.01** Amelia wakes in the sanctuary. Discovers her hematocrit is 28%."
        result = _reconcile_entries(old, new)
        assert "hematocrit" in result

    def test_timeline_single_line_old_wins_if_new_is_placeholder(self):
        old = "**01.01.01** Amelia wakes in the sanctuary."
        new = "**01.01.01** [TODO — outcome summary]"
        result = _reconcile_entries(old, new)
        assert "Amelia wakes" in result

    def test_identical_entries_unchanged(self):
        result = _reconcile_entries(CAST_ENTRY_ALICE, CAST_ENTRY_ALICE)
        assert result == CAST_ENTRY_ALICE.rstrip()

    def test_parse_failure_returns_old(self):
        # Simulate a scenario where an exception would occur — use a deliberately
        # mangled new_entry to ensure we get old back (graceful fallback).
        old = "### Alice\n- **Age:** 24\n"
        # Full-CAST new entry is valid, so test fallback via a different mechanism:
        # passing empty new entry means all blocks are empty — old is effectively returned
        new = ""
        result = _reconcile_entries(old, new)
        # Should not crash and should contain old content
        assert "Alice" in result


# ---------------------------------------------------------------------------
# _replace_entry_in_content
# ---------------------------------------------------------------------------

class TestReplaceEntryInContent:
    def test_replaces_entry(self):
        content = "### Alice\n- **Age:** 24\n\n### Bob\n- **Age:** 30\n"
        old = "### Alice\n- **Age:** 24"
        new = "### Alice\n- **Age:** 25"
        result = _replace_entry_in_content(content, old, new)
        assert "- **Age:** 25" in result
        assert "- **Age:** 24" not in result
        assert "Bob" in result  # other entries intact

    def test_no_op_when_old_not_found(self):
        content = "### Bob\n- **Age:** 30\n"
        result = _replace_entry_in_content(content, "### NotHere\n...", "### NotHere\nNew")
        assert result == content

    def test_no_op_on_empty_old(self):
        content = "### Bob\n"
        result = _replace_entry_in_content(content, "", "something")
        assert result == content

    def test_only_first_occurrence_replaced(self):
        content = "### Alice\n- **Age:** 24\n\n### Alice\n- **Age:** 24\n"
        old = "### Alice\n- **Age:** 24"
        new = "### Alice\n- **Age:** 25"
        result = _replace_entry_in_content(content, old, new)
        assert result.count("- **Age:** 25") == 1
        assert result.count("- **Age:** 24") == 1  # second occurrence unchanged


# ---------------------------------------------------------------------------
# format_report
# ---------------------------------------------------------------------------

class TestFormatReport:
    def _base_report(self, **overrides) -> dict:
        base = {
            "scene_id": "01.01.01",
            "cast":     {"added": [], "skipped": [], "reconciled": []},
            "glossary": {"added": [], "skipped": [], "reconciled": []},
            "threads":  {"added": [], "advanced": [], "closed": [], "reconciled": []},
            "timeline": {"added": [], "skipped": [], "reconciled": []},
        }
        base.update(overrides)
        return base

    def test_empty_report_no_entries(self):
        report = self._base_report()
        text = format_report(report)
        assert "No new entries" in text

    def test_added_entries_shown(self):
        report = self._base_report(cast={"added": ["Alice"], "skipped": [], "reconciled": []})
        text = format_report(report)
        assert "Alice" in text
        assert "CAST" in text

    def test_reconciled_entries_shown(self):
        report = self._base_report(
            cast={"added": [], "skipped": [], "reconciled": ["Alice"]},
        )
        text = format_report(report)
        assert "Alice" in text
        assert "Reconciled" in text

    def test_skipped_entries_shown(self):
        report = self._base_report(
            glossary={"added": [], "skipped": ["Breach Gates"], "reconciled": []},
        )
        text = format_report(report)
        assert "Breach Gates" in text
        assert "no new info" in text.lower()

    def test_threads_advanced_shown(self):
        report = self._base_report(
            threads={"added": [], "advanced": ["vault_mystery"], "closed": [], "reconciled": []},
        )
        text = format_report(report)
        assert "vault_mystery" in text
        assert "manually" in text.lower()

    def test_reconciled_count_in_summary(self):
        report = self._base_report(
            cast={"added": [], "skipped": [], "reconciled": ["Alice", "Bob"]},
        )
        text = format_report(report)
        assert "2" in text
        assert "reconciled" in text.lower()

    def test_error_shown(self):
        report = self._base_report()
        report["error"] = "LLM timeout"
        text = format_report(report)
        assert "LLM timeout" in text

    def test_backward_compat_missing_reconciled_key(self):
        """format_report must handle old-style reports that lack 'reconciled' key."""
        report = {
            "scene_id": "01.01.01",
            "cast":     {"added": ["Alice"], "skipped": []},
            "glossary": {"added": [], "skipped": []},
            "threads":  {"added": [], "advanced": [], "closed": []},
            "timeline": {"added": [], "skipped": []},
        }
        # Should not raise
        text = format_report(report)
        assert "Alice" in text


# ---------------------------------------------------------------------------
# scan_scene_for_index_entries — integration tests with mocked LLM
# ---------------------------------------------------------------------------

class TestScanSceneForIndexEntries:
    """Integration-level tests that mock the run_index_extraction LLM call."""

    SCENE_CONTENT = (
        "@@META\nID: 01.02.01\n@@\n"
        "Alice walked into the vault. She noticed the vault_mystery deepen."
    )

    @pytest.fixture
    def tmp_project(self, tmp_path: Path) -> Path:
        """Create a minimal project directory with empty index files."""
        for name in ("CAST.md", "GLOSSARY.md", "THREADS.md", "TIMELINE.md"):
            (tmp_path / name).write_text(f"# {name.replace('.md', '')}\n\n", encoding="utf-8")
        return tmp_path

    @pytest.fixture
    def tmp_project_with_alice(self, tmp_path: Path) -> Path:
        """Project where Alice already exists in CAST.md with TODO fields."""
        (tmp_path / "CAST.md").write_text(
            "# CAST\n\n## Supporting Characters\n\n"
            "### Alice\n- **Age:** [TODO]\n- **Role:** [TODO]\n- **Physical:** [TODO]\n\n",
            encoding="utf-8",
        )
        for name in ("GLOSSARY.md", "THREADS.md", "TIMELINE.md"):
            (tmp_path / name).write_text(f"# {name.replace('.md', '')}\n\n", encoding="utf-8")
        return tmp_path

    # --- New entry (no duplicate) ---

    @pytest.mark.asyncio
    @patch("lit_platform.services.index_service.run_index_extraction", new_callable=AsyncMock)
    async def test_new_character_added_to_cast(self, mock_extract, tmp_project):
        mock_extract.return_value = {
            "cast": [{"name": "Bob", "category": "supporting",
                      "draft_entry": "### Bob\n- **Age:** 30\n- **Role:** Guard\n"}],
            "glossary": [],
            "threads": [],
            "timeline": [],
        }
        report = await scan_scene_for_index_entries(
            scene_content=self.SCENE_CONTENT,
            project_path=tmp_project,
            indexes={},
            client=object(),
        )
        assert "Bob" in report["cast"]["added"]
        assert "Bob" not in report["cast"]["skipped"]
        assert "Bob" not in report["cast"]["reconciled"]
        cast_text = (tmp_project / "CAST.md").read_text(encoding="utf-8")
        assert "### Bob" in cast_text
        assert "⚡ auto" in cast_text

    @pytest.mark.asyncio
    @patch("lit_platform.services.index_service.run_index_extraction", new_callable=AsyncMock)
    async def test_new_glossary_term_added(self, mock_extract, tmp_project):
        mock_extract.return_value = {
            "cast": [],
            "glossary": [{"term": "Luminar Stone", "category": "term",
                          "draft_entry": "### Luminar Stone\n**Definition:** A glowing stone.\n**First seen:** 01.02.01\n**Notes:** Always capitalized.\n"}],
            "threads": [],
            "timeline": [],
        }
        report = await scan_scene_for_index_entries(
            scene_content=self.SCENE_CONTENT,
            project_path=tmp_project,
            indexes={},
            client=object(),
        )
        assert "Luminar Stone" in report["glossary"]["added"]
        glossary_text = (tmp_project / "GLOSSARY.md").read_text(encoding="utf-8")
        assert "Luminar Stone" in glossary_text

    @pytest.mark.asyncio
    @patch("lit_platform.services.index_service.run_index_extraction", new_callable=AsyncMock)
    async def test_new_thread_added(self, mock_extract, tmp_project):
        mock_extract.return_value = {
            "cast": [],
            "glossary": [],
            "threads": [{"thread_id": "vault_mystery", "action": "new",
                         "draft_entry": "### vault_mystery\n**Opened:** 01.02.01\n**Question:** What is in the vault?\n**Status:** Active.\n**Notes:** [TODO]\n"}],
            "timeline": [],
        }
        report = await scan_scene_for_index_entries(
            scene_content=self.SCENE_CONTENT,
            project_path=tmp_project,
            indexes={},
            client=object(),
        )
        assert "vault_mystery" in report["threads"]["added"]
        threads_text = (tmp_project / "THREADS.md").read_text(encoding="utf-8")
        assert "vault_mystery" in threads_text

    # --- Reconciliation ---

    @pytest.mark.asyncio
    @patch("lit_platform.services.index_service.run_index_extraction", new_callable=AsyncMock)
    async def test_existing_character_reconciled_when_new_info_available(
        self, mock_extract, tmp_project_with_alice
    ):
        """Existing entry with [TODO] fields gets updated with real values from LLM."""
        mock_extract.return_value = {
            "cast": [{"name": "Alice", "category": "supporting",
                      "draft_entry": "### Alice\n- **Age:** 24\n- **Role:** Sanctuary warden\n- **Physical:** 168cm\n"}],
            "glossary": [],
            "threads": [],
            "timeline": [],
        }
        report = await scan_scene_for_index_entries(
            scene_content=self.SCENE_CONTENT,
            project_path=tmp_project_with_alice,
            indexes={"CAST.md": (tmp_project_with_alice / "CAST.md").read_text()},
            client=object(),
        )
        assert "Alice" in report["cast"]["reconciled"]
        assert "Alice" not in report["cast"]["added"]
        assert "Alice" not in report["cast"]["skipped"]
        cast_text = (tmp_project_with_alice / "CAST.md").read_text(encoding="utf-8")
        assert "24" in cast_text
        assert "Sanctuary warden" in cast_text

    @pytest.mark.asyncio
    @patch("lit_platform.services.index_service.run_index_extraction", new_callable=AsyncMock)
    async def test_existing_character_skipped_when_no_new_info(
        self, mock_extract, tmp_project_with_alice
    ):
        """If the new draft adds nothing, the entry is reported as skipped."""
        # New draft is identical to what's already in the file
        mock_extract.return_value = {
            "cast": [{"name": "Alice", "category": "supporting",
                      "draft_entry": "### Alice\n- **Age:** [TODO]\n- **Role:** [TODO]\n- **Physical:** [TODO]\n"}],
            "glossary": [],
            "threads": [],
            "timeline": [],
        }
        report = await scan_scene_for_index_entries(
            scene_content=self.SCENE_CONTENT,
            project_path=tmp_project_with_alice,
            indexes={"CAST.md": (tmp_project_with_alice / "CAST.md").read_text()},
            client=object(),
        )
        assert "Alice" in report["cast"]["skipped"]
        assert "Alice" not in report["cast"]["reconciled"]

    @pytest.mark.asyncio
    @patch("lit_platform.services.index_service.run_index_extraction", new_callable=AsyncMock)
    async def test_existing_thread_reconciled(self, mock_extract, tmp_project):
        """Thread marked action='new' but already present → reconciled, not advanced."""
        (tmp_project / "THREADS.md").write_text(
            "# THREADS\n\n## Active Threads\n\n"
            "### vault_mystery\n**Opened:** 01.01.02\n**Question:** What is in the vault?\n"
            "**Status:** Active.\n**Notes:** [TODO]\n",
            encoding="utf-8",
        )
        mock_extract.return_value = {
            "cast": [],
            "glossary": [],
            "threads": [{"thread_id": "vault_mystery", "action": "new",
                         "draft_entry": "### vault_mystery\n**Opened:** 01.03.01\n"
                                        "**Question:** What is in the vault? Who sealed it?\n"
                                        "**Status:** Active. Vault door found ajar.\n"
                                        "**Notes:** Connected to ward collapse.\n"}],
            "timeline": [],
        }
        report = await scan_scene_for_index_entries(
            scene_content=self.SCENE_CONTENT,
            project_path=tmp_project,
            indexes={"THREADS.md": (tmp_project / "THREADS.md").read_text()},
            client=object(),
        )
        assert "vault_mystery" in report["threads"]["reconciled"]
        assert "vault_mystery" not in report["threads"]["advanced"]
        threads_text = (tmp_project / "THREADS.md").read_text(encoding="utf-8")
        # Opened field must keep original scene (immutable)
        assert "01.01.02" in threads_text
        # New question and notes must appear
        assert "Who sealed it?" in threads_text
        assert "Connected to ward collapse." in threads_text

    @pytest.mark.asyncio
    @patch("lit_platform.services.index_service.run_index_extraction", new_callable=AsyncMock)
    async def test_timeline_entry_reconciled(self, mock_extract, tmp_project):
        """Existing timeline entry is updated when a richer summary is proposed."""
        (tmp_project / "TIMELINE.md").write_text(
            "# TIMELINE\n\n## Part 01\n\n### Chapter 01\n\n"
            "**01.01.01** [TODO — outcome summary]\n",
            encoding="utf-8",
        )
        mock_extract.return_value = {
            "cast": [],
            "glossary": [],
            "threads": [],
            "timeline": [{"scene_id": "01.01.01", "part": "01", "chapter": "01",
                          "summary": "Amelia wakes. Hematocrit is 28%. George is missing.",
                          "draft_entry": "**01.01.01** Amelia wakes. Hematocrit is 28%. George is missing."}],
        }
        report = await scan_scene_for_index_entries(
            scene_content=self.SCENE_CONTENT,
            project_path=tmp_project,
            indexes={"TIMELINE.md": (tmp_project / "TIMELINE.md").read_text()},
            client=object(),
        )
        assert "01.01.01" in report["timeline"]["reconciled"]
        timeline_text = (tmp_project / "TIMELINE.md").read_text(encoding="utf-8")
        assert "Hematocrit is 28%" in timeline_text
        assert "[TODO — outcome summary]" not in timeline_text

    # --- Error handling ---

    @pytest.mark.asyncio
    @patch("lit_platform.services.index_service.run_index_extraction", new_callable=AsyncMock)
    async def test_llm_error_propagated_in_report(self, mock_extract, tmp_project):
        mock_extract.return_value = {
            "cast": [], "glossary": [], "threads": [], "timeline": [],
            "error": "LLM request timed out",
        }
        report = await scan_scene_for_index_entries(
            scene_content=self.SCENE_CONTENT,
            project_path=tmp_project,
            indexes={},
            client=object(),
        )
        assert "error" in report
        assert "timed out" in report["error"]

    @pytest.mark.asyncio
    @patch("lit_platform.services.index_service.run_index_extraction", new_callable=AsyncMock)
    @patch("lit_platform.services.index_service.audit_indexes_deterministic")
    async def test_preflight_audit_enabled_adds_non_blocking_warning(
        self,
        mock_audit,
        mock_extract,
        tmp_project,
    ):
        mock_extract.return_value = {
            "cast": [],
            "glossary": [],
            "threads": [],
            "timeline": [],
        }
        mock_audit.return_value = SimpleNamespace(
            deterministic=[SimpleNamespace(check_id="placeholder_density")]
        )

        with patch.dict("os.environ", {"LIT_CRITIC_INDEX_PREFLIGHT_AUDIT": "1"}, clear=False):
            report = await scan_scene_for_index_entries(
                scene_content=self.SCENE_CONTENT,
                project_path=tmp_project,
                indexes={"CAST.md": ""},
                client=object(),
            )

        mock_audit.assert_called_once_with({"CAST.md": ""})
        assert "preflight_warning" in report
        assert "scan will continue" in report["preflight_warning"].lower()
        assert report["preflight_findings_count"] == 1

    @pytest.mark.asyncio
    @patch("lit_platform.services.index_service.run_index_extraction", new_callable=AsyncMock)
    @patch("lit_platform.services.index_service.audit_indexes_deterministic")
    async def test_preflight_audit_disabled_skips_audit_call(
        self,
        mock_audit,
        mock_extract,
        tmp_project,
    ):
        mock_extract.return_value = {
            "cast": [],
            "glossary": [],
            "threads": [],
            "timeline": [],
        }

        with patch.dict("os.environ", {"LIT_CRITIC_INDEX_PREFLIGHT_AUDIT": "0"}, clear=False):
            report = await scan_scene_for_index_entries(
                scene_content=self.SCENE_CONTENT,
                project_path=tmp_project,
                indexes={"CAST.md": ""},
                client=object(),
            )

        mock_audit.assert_not_called()
        assert "preflight_warning" not in report

    @pytest.mark.asyncio
    @patch("lit_platform.services.index_service.run_index_extraction", new_callable=AsyncMock)
    @patch("lit_platform.services.index_service.audit_indexes_deterministic", side_effect=RuntimeError("audit unavailable"))
    async def test_preflight_audit_failure_is_non_blocking(
        self,
        _mock_audit,
        mock_extract,
        tmp_project,
    ):
        mock_extract.return_value = {
            "cast": [],
            "glossary": [],
            "threads": [],
            "timeline": [],
        }

        with patch.dict("os.environ", {"LIT_CRITIC_INDEX_PREFLIGHT_AUDIT": "true"}, clear=False):
            report = await scan_scene_for_index_entries(
                scene_content=self.SCENE_CONTENT,
                project_path=tmp_project,
                indexes={"CAST.md": ""},
                client=object(),
            )

        assert "preflight_warning" in report
        assert "non-blocking" in report["preflight_warning"].lower()
        assert "audit unavailable" in report["preflight_warning"]


class TestFormatReportPreflight:
    def test_format_report_includes_preflight_warning(self):
        report = {
            "scene_id": "01.02.01",
            "preflight_warning": "Index preflight audit found 2 deterministic issue(s); scan will continue.",
            "cast": {"added": [], "skipped": [], "reconciled": []},
            "glossary": {"added": [], "skipped": [], "reconciled": []},
            "threads": {"added": [], "advanced": [], "closed": [], "reconciled": []},
            "timeline": {"added": [], "skipped": [], "reconciled": []},
        }

        text = format_report(report)
        assert "Index preflight audit found 2 deterministic issue(s)" in text


class TestGetIndexCoverageGaps:
    def test_reports_unreferenced_entries_with_source_attribution(self, tmp_path: Path):
        (tmp_path / "CAST.md").write_text(
            "# CAST\n\n"
            "## Supporting Characters\n\n"
            "### Alice\n"
            "- **Role:** Warden\n\n"
            "### Bob\n"
            "- **Role:** Scout\n",
            encoding="utf-8",
        )
        (tmp_path / "GLOSSARY.md").write_text(
            "# GLOSSARY\n\n"
            "## Terms\n\n"
            "### Breach Gate\n"
            "**Definition:** Portal\n\n"
            "### Sanctum\n"
            "**Definition:** Citadel\n",
            encoding="utf-8",
        )

        scenes_dir = tmp_path / "scenes"
        scenes_dir.mkdir()
        (scenes_dir / "01.md").write_text("Alice enters the Breach Gate.", encoding="utf-8")
        (scenes_dir / "02.md").write_text("The Sanctum remains sealed.", encoding="utf-8")

        with patch(
            "lit_platform.services.index_service._load_reviewed_scene_paths",
            return_value=["scenes/01.md", "scenes/02.md"],
        ):
            report = get_index_coverage_gaps(tmp_path)

        assert report["summary"]["reviewed_scene_count"] == 2
        assert report["summary"]["indexed_entry_count"] == 4
        assert report["summary"]["gap_count"] == 1
        assert report["rows"] == [
            {
                "scope": "cast",
                "entry": "Bob",
                "source_file": "CAST.md",
                "source_section": "Supporting Characters",
                "source_line": 8,
                "referenced_scene_paths": [],
            }
        ]

    def test_scope_filter_limits_report_to_glossary(self, tmp_path: Path):
        (tmp_path / "CAST.md").write_text(
            "# CAST\n\n## Supporting Characters\n\n### Alice\n- **Role:** Warden\n",
            encoding="utf-8",
        )
        (tmp_path / "GLOSSARY.md").write_text(
            "# GLOSSARY\n\n## Terms\n\n### Breach Gate\n**Definition:** Portal\n",
            encoding="utf-8",
        )

        with patch(
            "lit_platform.services.index_service._load_reviewed_scene_paths",
            return_value=[],
        ):
            report = get_index_coverage_gaps(tmp_path, scopes=["glossary"])

        assert report["filters"]["scopes"] == ["glossary"]
        assert report["summary"]["indexed_entry_count"] == 1
        assert report["summary"]["gap_count"] == 1
        assert report["rows"][0]["scope"] == "glossary"
        assert report["rows"][0]["entry"] == "Breach Gate"

    def test_unsupported_scope_raises_value_error(self, tmp_path: Path):
        with pytest.raises(ValueError, match="Unsupported index coverage scope"):
            get_index_coverage_gaps(tmp_path, scopes=["threads"])

    def test_missing_scene_paths_are_reported_non_blocking(self, tmp_path: Path):
        (tmp_path / "CAST.md").write_text(
            "# CAST\n\n## Supporting Characters\n\n### Alice\n- **Role:** Warden\n",
            encoding="utf-8",
        )
        (tmp_path / "GLOSSARY.md").write_text("# GLOSSARY\n", encoding="utf-8")

        with patch(
            "lit_platform.services.index_service._load_reviewed_scene_paths",
            return_value=["scenes/missing.md"],
        ):
            report = get_index_coverage_gaps(tmp_path, scopes=["cast"])

        assert report["reviewed_scene_paths"] == ["scenes/missing.md"]
        assert report["missing_scene_paths"] == ["scenes/missing.md"]
        assert report["summary"]["reviewed_scene_count"] == 1
        assert report["summary"]["gap_count"] == 1
        assert report["rows"][0]["entry"] == "Alice"


class TestGetFindingIndexContext:
    def test_matches_cast_and_glossary_entries_from_finding_fields(self, tmp_path: Path):
        (tmp_path / "CAST.md").write_text(
            "# CAST\n\n"
            "## Supporting Characters\n\n"
            "### Alice\n"
            "- **Role:** Warden\n\n"
            "### Bob\n"
            "- **Role:** Scout\n",
            encoding="utf-8",
        )
        (tmp_path / "GLOSSARY.md").write_text(
            "# GLOSSARY\n\n"
            "## Terms\n\n"
            "### Breach Gate\n"
            "**Definition:** Portal\n\n"
            "### Sanctum\n"
            "**Definition:** Citadel\n",
            encoding="utf-8",
        )

        finding = {
            "location": "Alice at gate",
            "evidence": "Alice enters the Breach Gate.",
            "impact": "Sanctum remains inaccessible.",
            "options": ["Ask Bob to verify timeline."],
        }

        report = get_finding_index_context(tmp_path, finding)

        assert report["summary"]["candidate_entry_count"] == 4
        assert report["summary"]["match_count"] == 4
        assert report["rows"] == [
            {
                "scope": "cast",
                "entry": "Alice",
                "source_file": "CAST.md",
                "source_section": "Supporting Characters",
                "source_line": 5,
                "matched_fields": ["location", "evidence"],
            },
            {
                "scope": "cast",
                "entry": "Bob",
                "source_file": "CAST.md",
                "source_section": "Supporting Characters",
                "source_line": 8,
                "matched_fields": ["options"],
            },
            {
                "scope": "glossary",
                "entry": "Breach Gate",
                "source_file": "GLOSSARY.md",
                "source_section": "Terms",
                "source_line": 5,
                "matched_fields": ["evidence"],
            },
            {
                "scope": "glossary",
                "entry": "Sanctum",
                "source_file": "GLOSSARY.md",
                "source_section": "Terms",
                "source_line": 8,
                "matched_fields": ["impact"],
            },
        ]

    def test_scope_filter_and_max_matches_per_scope_are_enforced(self, tmp_path: Path):
        (tmp_path / "CAST.md").write_text(
            "# CAST\n\n## Supporting Characters\n\n### Alice\n- **Role:** Warden\n",
            encoding="utf-8",
        )
        (tmp_path / "GLOSSARY.md").write_text(
            "# GLOSSARY\n\n## Terms\n\n### Breach Gate\n**Definition:** Portal\n\n### Sanctum\n**Definition:** Citadel\n",
            encoding="utf-8",
        )

        finding = {
            "evidence": "Breach Gate appears before Sanctum.",
        }

        report = get_finding_index_context(
            tmp_path,
            finding,
            scopes=["glossary"],
            max_matches_per_scope=1,
        )

        assert report["filters"]["scopes"] == ["glossary"]
        assert report["filters"]["max_matches_per_scope"] == 1
        assert report["summary"]["candidate_entry_count"] == 2
        assert report["summary"]["match_count"] == 1
        assert report["rows"][0]["scope"] == "glossary"
        assert report["rows"][0]["entry"] == "Breach Gate"
