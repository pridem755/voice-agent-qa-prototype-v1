import re
from pathlib import Path
import pytest
from report_generator import ReportGenerator

#---------------------------------------------------------------------------
# Unit tests for the ReportGenerator class, which compiles test run results into a markdown report
#---------------------------------------------------------------------------
class TestFormatDuration:

    @pytest.mark.parametrize("seconds,expected", [
        (0, "0s"),
        (45, "45s"),
        (59, "59s"),
        (60, "1m 0s"),
        (90, "1m 30s"),
        (135, "2m 15s"),
        (3600, "60m 0s"),
    ])
    def test_format_duration(self, seconds, expected):
        assert ReportGenerator._format_duration(seconds) == expected

#---------------------------------------------------------------------------
# Tests for the ReportGenerator's main generate() method, using sample data from the BugAnalyzer
#---------------------------------------------------------------------------
class TestGenerateReport:
    def test_creates_report_file(self, tmp_path, sample_run_results, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        gen = ReportGenerator()
        path = gen.generate(results=sample_run_results, total_duration=293.0)

        assert path.exists()
        assert path.suffix == ".md"

    def test_report_contains_header(self, tmp_path, sample_run_results, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        gen = ReportGenerator()
        path = gen.generate(results=sample_run_results, total_duration=293.0)
        content = path.read_text()

        assert "# Voice Bot Test Run Report" in content

    def test_report_contains_total_calls(self, tmp_path, sample_run_results, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        gen = ReportGenerator()
        path = gen.generate(results=sample_run_results, total_duration=293.0)
        content = path.read_text()

        assert "3" in content 

    def test_report_contains_bug_summary_section(
        self, tmp_path, sample_run_results, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        gen = ReportGenerator()
        path = gen.generate(results=sample_run_results, total_duration=293.0)
        content = path.read_text()

        assert "## Bug Summary by Severity" in content

    def test_report_severity_table_has_all_levels(
        self, tmp_path, sample_run_results, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        gen = ReportGenerator()
        path = gen.generate(results=sample_run_results, total_duration=293.0)
        content = path.read_text()

        assert "Critical" in content
        assert "High" in content
        assert "Medium" in content
        assert "Low" in content

    def test_report_contains_call_results_table(
        self, tmp_path, sample_run_results, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        gen = ReportGenerator()
        path = gen.generate(results=sample_run_results, total_duration=293.0)
        content = path.read_text()

        assert "## Call Results" in content

    def test_report_contains_scenario_names(
        self, tmp_path, sample_run_results, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        gen = ReportGenerator()
        path = gen.generate(results=sample_run_results, total_duration=293.0)
        content = path.read_text()

        assert "Simple Appointment Scheduling" in content
        assert "Urgent Symptoms" in content

    def test_report_contains_all_bugs_section(
        self, tmp_path, sample_run_results, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        gen = ReportGenerator()
        path = gen.generate(results=sample_run_results, total_duration=293.0)
        content = path.read_text()

        assert "## All Bugs Found" in content

    def test_report_contains_bug_descriptions(
        self, tmp_path, sample_run_results, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        gen = ReportGenerator()
        path = gen.generate(results=sample_run_results, total_duration=293.0)
        content = path.read_text()

        assert "Agent confirmed Sunday appointment" in content

    def test_report_contains_bug_categories_section(
        self, tmp_path, sample_run_results, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        gen = ReportGenerator()
        path = gen.generate(results=sample_run_results, total_duration=293.0)
        content = path.read_text()

        assert "## Bug Categories" in content

    def test_empty_run_no_bugs_message(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        empty_results = [
            {
                "scenario_id": "01",
                "scenario_name": "Clean Call",
                "call_sid": "CA000",
                "status": "completed",
                "transcript_path": "transcripts/CA000.json",
                "bugs": [],
                "duration_seconds": 90.0,
                "error": None,
            }
        ]

        gen = ReportGenerator()
        path = gen.generate(results=empty_results, total_duration=90.0)
        content = path.read_text()

        assert "No bugs found" in content

    def test_report_filename_contains_timestamp(
        self, tmp_path, sample_run_results, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        gen = ReportGenerator()
        path = gen.generate(results=sample_run_results, total_duration=100.0)
        assert re.match(r"run_report_\d{8}_\d{6}\.md", path.name)

    def test_failed_call_shown_in_results(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        results_with_failure = [
            {
                "scenario_id": "01",
                "scenario_name": "Failed Call Test",
                "call_sid": "CA_FAIL",
                "status": "failed",
                "transcript_path": None,
                "bugs": [],
                "duration_seconds": 10.0,
                "error": "Call failed to connect",
            }
        ]

        gen = ReportGenerator()
        path = gen.generate(results=results_with_failure, total_duration=10.0)
        content = path.read_text()

        assert "failed" in content
        assert "Failed Call Test" in content
