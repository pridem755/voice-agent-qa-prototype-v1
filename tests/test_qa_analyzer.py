from pathlib import Path
import pytest
from qa_analyzer import QAAnalyzer


class TestAnalyzeTranscript:
    """Tests for analyzing individual transcripts."""
    
    @pytest.mark.asyncio
    async def test_returns_analysis_string(
        self,
        sample_transcript_file,
        mock_openai_analysis_response,
    ):
        """Verifying analyze_transcript returns markdown string."""
        analyzer = QAAnalyzer()
        analyzer._client = mock_openai_analysis_response
        
        result = await analyzer.analyze_transcript(sample_transcript_file)
        
        assert isinstance(result, str)
        assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_returns_bug_markdown_format(
        self,
        sample_transcript_file,
        mock_openai_analysis_response,
    ):
        """Checking analysis contains bug markdown format."""
        analyzer = QAAnalyzer()
        analyzer._client = mock_openai_analysis_response
        
        result = await analyzer.analyze_transcript(sample_transcript_file)
        
        assert "### Bug:" in result
        assert "**Severity**:" in result
    
    @pytest.mark.asyncio
    async def test_handles_missing_file(self, tmp_path):
        """Ensuring missing files are handled gracefully."""
        analyzer = QAAnalyzer()
        missing_file = tmp_path / "nonexistent.txt"
        
        result = await analyzer.analyze_transcript(missing_file)
        
        assert result == ""
    
    @pytest.mark.asyncio
    async def test_handles_api_error(self, sample_transcript_file):
        """Checking API errors are handled without crashing."""
        from unittest.mock import AsyncMock
        
        analyzer = QAAnalyzer()
        analyzer._client = AsyncMock()
        analyzer._client.chat.completions.create = AsyncMock(
            side_effect=Exception("API error")
        )
        
        result = await analyzer.analyze_transcript(sample_transcript_file)
        
        assert "Analysis failed" in result


class TestAnalyzeAll:
    """Tests for analyzing multiple transcripts."""
    
    @pytest.mark.asyncio
    async def test_creates_bug_report(
        self,
        tmp_path,
        sample_transcript_file,
        mock_openai_analysis_response,
        monkeypatch,
    ):
        """Verifying bug report is created."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()
        
        # Moving sample transcript to transcripts dir
        transcripts_dir = tmp_path / "transcripts"
        transcripts_dir.mkdir()
        new_path = transcripts_dir / sample_transcript_file.name
        new_path.write_text(sample_transcript_file.read_text())
        
        analyzer = QAAnalyzer()
        analyzer._client = mock_openai_analysis_response
        
        await analyzer.analyze_all(transcripts_dir)
        
        bug_report = tmp_path / "reports" / "bug_report.md"
        assert bug_report.exists()
    
    @pytest.mark.asyncio
    async def test_creates_run_summary(
        self,
        tmp_path,
        sample_transcript_file,
        mock_openai_analysis_response,
        monkeypatch,
    ):
        """Checking run summary is created."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()
        
        transcripts_dir = tmp_path / "transcripts"
        transcripts_dir.mkdir()
        new_path = transcripts_dir / sample_transcript_file.name
        new_path.write_text(sample_transcript_file.read_text())
        
        analyzer = QAAnalyzer()
        analyzer._client = mock_openai_analysis_response
        
        await analyzer.analyze_all(transcripts_dir)
        
        summary = tmp_path / "reports" / "run_summary.md"
        assert summary.exists()
    
    @pytest.mark.asyncio
    async def test_bug_report_contains_analysis(
        self,
        tmp_path,
        sample_transcript_file,
        mock_openai_analysis_response,
        monkeypatch,
    ):
        """Verifying bug report contains analysis results."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()
        
        transcripts_dir = tmp_path / "transcripts"
        transcripts_dir.mkdir()
        new_path = transcripts_dir / sample_transcript_file.name
        new_path.write_text(sample_transcript_file.read_text())
        
        analyzer = QAAnalyzer()
        analyzer._client = mock_openai_analysis_response
        
        await analyzer.analyze_all(transcripts_dir)
        
        bug_report = tmp_path / "reports" / "bug_report.md"
        content = bug_report.read_text()
        
        assert "Bug Report" in content
        assert sample_transcript_file.name in content
    
    @pytest.mark.asyncio
    async def test_handles_empty_transcripts_dir(self, tmp_path, monkeypatch):
        """Checking empty transcripts directory is handled."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()
        
        transcripts_dir = tmp_path / "transcripts"
        transcripts_dir.mkdir()
        
        analyzer = QAAnalyzer()
        
        # Should not crash
        await analyzer.analyze_all(transcripts_dir)
    
    @pytest.mark.asyncio
    async def test_counts_bugs_in_summary(
        self,
        tmp_path,
        sample_transcript_file,
        mock_openai_analysis_response,
        monkeypatch,
    ):
        """Verifying bug count is included in summary."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()
        
        transcripts_dir = tmp_path / "transcripts"
        transcripts_dir.mkdir()
        new_path = transcripts_dir / sample_transcript_file.name
        new_path.write_text(sample_transcript_file.read_text())
        
        analyzer = QAAnalyzer()
        analyzer._client = mock_openai_analysis_response
        
        await analyzer.analyze_all(transcripts_dir)
        
        summary = tmp_path / "reports" / "run_summary.md"
        content = summary.read_text()
        
        assert "Issues found" in content
    
    @pytest.mark.asyncio
    async def test_processes_multiple_transcripts(
        self,
        tmp_path,
        sample_transcript_text,
        mock_openai_analysis_response,
        monkeypatch,
    ):
        """Checking multiple transcripts are processed."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()
        
        transcripts_dir = tmp_path / "transcripts"
        transcripts_dir.mkdir()
        
        # Creating multiple transcript files
        for i in range(3):
            path = transcripts_dir / f"transcript_{i}.txt"
            path.write_text(sample_transcript_text, encoding="utf-8")
        
        analyzer = QAAnalyzer()
        analyzer._client = mock_openai_analysis_response
        
        await analyzer.analyze_all(transcripts_dir)
        
        summary = tmp_path / "reports" / "run_summary.md"
        content = summary.read_text()
        
        assert "Calls completed | 3" in content
