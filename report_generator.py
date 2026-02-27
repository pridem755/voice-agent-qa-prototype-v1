import json
import logging
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REPORTS_DIR = Path("reports")

#---------------------------------------------------------------------------
#ReportGenerator: builds a comprehensive Markdown report summarizing the test run, including all bugs found
#---------------------------------------------------------------------------
class ReportGenerator:
    def generate(
        self,
        results: list[dict],
        total_duration: float,
    ) -> Path:
        #Ensuring reports directory exists and create a timestamped report filename
        REPORTS_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_path = REPORTS_DIR / f"run_report_{timestamp}.md"

        #Gathering all bugs across all calls
        all_bugs = []
        for result in results:
            for bug in result.get("bugs", []):
                bug_with_context = {
                    **bug,
                    "call_sid": result.get("call_sid", "unknown"),
                    "scenario_name": result.get("scenario_name", "unknown"),
                    "transcript_path": result.get("transcript_path", ""),
                }
                all_bugs.append(bug_with_context)

        #Counting stats
        severity_counts = Counter(b.get("severity") for b in all_bugs)
        category_counts = Counter(b.get("category") for b in all_bugs)
        total_calls = len(results)
        successful_calls = sum(1 for r in results if r["status"] == "completed")

        lines = []

        #---- Report header and summary stats --------------------------------------
        lines += [
            "# Voice Bot Test Run Report",
            "",
            f"**Generated:** {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Total calls:** {total_calls} ({successful_calls} completed)",
            f"**Total runtime:** {self._format_duration(total_duration)}",
            f"**Total bugs found:** {len(all_bugs)}",
            "",
        ]

        #---- Severity summary ------------------------------------------------------
        lines += [
            "## Bug Summary by Severity",
            "",
            "| Severity | Count |",
            "|----------|-------|",
        ]
        for sev in ("critical", "high", "medium", "low"):
            count = severity_counts.get(sev, 0)
            lines.append(f"| {sev.capitalize()} | {count} |")
        lines.append("")

        #---- Call results table ------------------------------------------------------
        lines += [
            "## Call Results",
            "",
            "| # | Scenario | Status | Duration | Bugs |",
            "|---|----------|--------|----------|------|",
        ]
        for i, result in enumerate(results, 1):
            status = result.get("status", "unknown")
            duration = self._format_duration(result.get("duration_seconds", 0))
            bug_count = len(result.get("bugs", []))
            name = result.get("scenario_name", "unknown")[:40]
            lines.append(f"| {i} | {name} | {status} | {duration} | {bug_count} |")
        lines.append("")

        #---- All bugs, grouped by severity ----------------------------------------
        lines += [
            "## All Bugs Found",
            "",
        ]

        if not all_bugs:
            lines.append("No bugs found across all calls.\n")
        else:
            for severity in ("critical", "high", "medium", "low"):
                severity_bugs = [b for b in all_bugs if b.get("severity") == severity]
                if not severity_bugs:
                    continue

                lines += [
                    f"### {severity.upper()} Severity ({len(severity_bugs)} bugs)",
                    "",
                ]

                for bug in severity_bugs:
                    lines += [
                        f"#### {bug.get('category', 'unknown').replace('_', ' ').title()}",
                        "",
                        f"- **Call:** `{bug.get('call_sid', 'unknown')}`",
                        f"- **Scenario:** {bug.get('scenario_name', 'unknown')}",
                        f"- **Transcript:** `{bug.get('transcript_path', 'N/A')}`",
                        f"- **Location:** {bug.get('transcript_location', 'unknown')}",
                        "",
                        f"**Description:** {bug.get('description', '')}",
                        "",
                        f"**Agent said:** \"{bug.get('agent_quote', '')}\"",
                        "",
                        f"**Expected:** {bug.get('expected_behavior', '')}",
                        "",
                        "---",
                        "",
                    ]

        #---- Bug categories breakdown -------------------------------------------
        if category_counts:
            lines += [
                "## Bug Categories",
                "",
                "| Category | Count |",
                "|----------|-------|",
            ]
            for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
                lines.append(f"| {cat.replace('_', ' ').title()} | {count} |")
            lines.append("")

        #---- Writing report to file -------------------------------------------------
        with open(report_path, "w") as f:
            f.write("\n".join(lines))

        logger.info(f"Run report saved: {report_path}")
        return report_path

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format seconds into a human-readable duration string."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
