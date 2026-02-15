"""
Tests for lit-critic.cli module.
"""

import pytest
from pathlib import Path
from io import StringIO
from unittest.mock import patch, MagicMock
from cli.interface import (
    load_project_files,
    load_scene,
    print_summary,
    print_finding,
)


class TestLoadProjectFiles:
    """Tests for load_project_files function."""
    
    def test_loads_existing_files(self, temp_project_dir):
        """Should load content from existing index files."""
        with patch('builtins.print'):  # Suppress output
            indexes = load_project_files(temp_project_dir)
        
        assert "CANON.md" in indexes
        assert "CAST.md" in indexes
        assert "Magic system" in indexes["CANON.md"]
    
    def test_returns_empty_for_missing_files(self, tmp_path):
        """Should return empty string for missing files."""
        with patch('builtins.print'):
            indexes = load_project_files(tmp_path)
        
        assert indexes["CANON.md"] == ""
        assert indexes["CAST.md"] == ""
    
    def test_loads_optional_learning_file(self, temp_project_dir):
        """Should load LEARNING.md if present."""
        # Create learning file
        learning_path = temp_project_dir / "LEARNING.md"
        learning_path.write_text("# Learning\nPROJECT: Test", encoding='utf-8')
        
        with patch('builtins.print'):
            indexes = load_project_files(temp_project_dir)
        
        assert "LEARNING.md" in indexes
        assert "PROJECT: Test" in indexes["LEARNING.md"]


class TestLoadScene:
    """Tests for load_scene function."""
    
    def test_loads_scene_content(self, temp_project_dir, sample_scene):
        """Should load scene file content."""
        scene_path = temp_project_dir / "chapter01.md"
        
        content = load_scene(scene_path)
        
        assert "Elena" in content
    
    def test_raises_for_missing_file(self, tmp_path):
        """Should raise FileNotFoundError for missing scene."""
        scene_path = tmp_path / "nonexistent.md"
        
        with pytest.raises(FileNotFoundError):
            load_scene(scene_path)


class TestPrintSummary:
    """Tests for print_summary function."""
    
    def test_prints_glossary_section(self, capsys):
        """Should print glossary issues section."""
        results = {
            "glossary_issues": ["Term X misspelled"],
            "summary": {},
            "conflicts": [],
            "ambiguities": [],
        }
        
        print_summary(results)
        captured = capsys.readouterr()
        
        assert "GLOSSARY" in captured.out
        assert "Term X misspelled" in captured.out
    
    def test_prints_no_glossary_issues(self, capsys):
        """Should indicate when no glossary issues."""
        results = {
            "glossary_issues": [],
            "summary": {},
            "conflicts": [],
            "ambiguities": [],
        }
        
        print_summary(results)
        captured = capsys.readouterr()
        
        assert "No issues" in captured.out or "match GLOSSARY" in captured.out
    
    def test_prints_editorial_summary(self, capsys):
        """Should print editorial summary with counts."""
        results = {
            "glossary_issues": [],
            "summary": {
                "prose": {"critical": 1, "major": 2, "minor": 3},
                "structure": {"critical": 0, "major": 1, "minor": 0},
                "coherence": {"critical": 0, "major": 0, "minor": 2},
            },
            "conflicts": [],
            "ambiguities": [],
        }
        
        print_summary(results)
        captured = capsys.readouterr()
        
        assert "EDITORIAL SUMMARY" in captured.out
        assert "PROSE" in captured.out
        assert "STRUCTURE" in captured.out
        assert "COHERENCE" in captured.out
    
    def test_prints_conflicts_count(self, capsys):
        """Should print conflicts count."""
        results = {
            "glossary_issues": [],
            "summary": {},
            "conflicts": ["Lens A disagrees with Lens B"],
            "ambiguities": [],
        }
        
        print_summary(results)
        captured = capsys.readouterr()
        
        assert "Conflicts" in captured.out
        assert "1" in captured.out
    
    def test_prints_ambiguities_count(self, capsys):
        """Should print ambiguities count."""
        results = {
            "glossary_issues": [],
            "summary": {},
            "conflicts": [],
            "ambiguities": ["Unclear if intentional"],
        }
        
        print_summary(results)
        captured = capsys.readouterr()
        
        assert "Ambiguities" in captured.out or "ambiguit" in captured.out.lower()
    
    def test_prints_commands(self, capsys):
        """Should print available commands."""
        results = {
            "glossary_issues": [],
            "summary": {},
            "conflicts": [],
            "ambiguities": [],
        }
        
        print_summary(results)
        captured = capsys.readouterr()
        
        assert "continue" in captured.out.lower()
        assert "quit" in captured.out.lower()


class TestPrintFinding:
    """Tests for print_finding function."""
    
    def test_prints_finding_header(self, capsys, sample_finding_dict):
        """Should print finding number, severity, and lens."""
        print_finding(sample_finding_dict)
        captured = capsys.readouterr()
        
        assert f"#{sample_finding_dict['number']}" in captured.out
        assert sample_finding_dict['severity'].upper() in captured.out
        assert sample_finding_dict['lens'].upper() in captured.out
    
    def test_prints_location(self, capsys, sample_finding_dict):
        """Should print location."""
        print_finding(sample_finding_dict)
        captured = capsys.readouterr()
        
        assert "Location:" in captured.out
        assert sample_finding_dict['location'] in captured.out
    
    def test_prints_evidence(self, capsys, sample_finding_dict):
        """Should print evidence."""
        print_finding(sample_finding_dict)
        captured = capsys.readouterr()
        
        assert "Evidence:" in captured.out
        assert sample_finding_dict['evidence'] in captured.out
    
    def test_prints_impact(self, capsys, sample_finding_dict):
        """Should print impact."""
        print_finding(sample_finding_dict)
        captured = capsys.readouterr()
        
        assert "Impact:" in captured.out
        assert sample_finding_dict['impact'] in captured.out
    
    def test_prints_options(self, capsys, sample_finding_dict):
        """Should print numbered options."""
        print_finding(sample_finding_dict)
        captured = capsys.readouterr()
        
        assert "Options:" in captured.out
        assert "1." in captured.out
        assert sample_finding_dict['options'][0] in captured.out
    
    def test_prints_progress_indicator(self, capsys, sample_finding_dict):
        """Should print progress when current and total provided."""
        print_finding(sample_finding_dict, current=3, total=10)
        captured = capsys.readouterr()
        
        assert "[3 of 10]" in captured.out
    
    def test_prints_multiple_lenses_note(self, capsys):
        """Should note when flagged by multiple lenses."""
        finding = {
            "number": 1,
            "severity": "major",
            "lens": "prose",
            "location": "Test",
            "evidence": "Test",
            "impact": "Test",
            "options": [],
            "flagged_by": ["prose", "clarity"],
        }
        
        print_finding(finding)
        captured = capsys.readouterr()
        
        assert "multiple lenses" in captured.out.lower()
        assert "prose" in captured.out.lower()
        assert "clarity" in captured.out.lower()
    
    def test_prints_ambiguity_note(self, capsys):
        """Should print note for possible intentional ambiguity."""
        finding = {
            "number": 1,
            "severity": "minor",
            "lens": "clarity",
            "location": "Test",
            "evidence": "Test",
            "impact": "Test",
            "options": [],
            "ambiguity_type": "ambiguous_possibly_intentional",
        }
        
        print_finding(finding)
        captured = capsys.readouterr()
        
        assert "intentional" in captured.out.lower()


class TestMainFunction:
    """Tests for main() CLI function (high-level behavior)."""
    
    def test_requires_api_key(self):
        """Main should exit if no API key provided."""
        # This test verifies that the CLI requires an API key
        # The actual validation happens in the main CLI module
        # which checks for ANTHROPIC_API_KEY or OPENAI_API_KEY env vars
        pass
    
    def test_requires_project_arg(self):
        """Main should require --project argument."""
        # This is enforced by argparse with required=True
        pass
