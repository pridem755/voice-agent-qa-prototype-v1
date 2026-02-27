import json
import logging
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

#---------------------------------------------------------------------------
#Bug data model
#---------------------------------------------------------------------------

@dataclass
#Represents a single bug found in the agent's behavior during a call.
class Bug:
    severity: str          
    category: str         
    description: str       
    agent_quote: str       
    expected_behavior: str 
    transcript_location: str 

    def to_dict(self) -> dict:
        return asdict(self)

    #Rendering as a markdown bug report entry for human reading.
    def to_markdown(self) -> str:
        severity_label = {
            "critical": "[CRITICAL]",
            "high": "[HIGH]",
            "medium": "[MEDIUM]",
            "low": "[LOW]",
        }.get(self.severity, "[UNKNOWN]")

        return (
            f"### {severity_label} {self.category.replace('_', ' ').title()}\n\n"
            f"**Description:** {self.description}\n\n"
            f"**Agent said:** \"{self.agent_quote}\"\n\n"
            f"**Expected:** {self.expected_behavior}\n\n"
            f"**Location:** {self.transcript_location}\n"
        )
#---------------------------------------------------------------------------
#Bug categories
#---------------------------------------------------------------------------
QA_CATEGORIES = [
    "scheduling_error",         
    "incorrect_information",    
    "hallucination",            
    "failed_to_clarify",        
    "premature_confirmation",   
    "no_answer",                
    "inappropriate_response",   
    "poor_ux",                  
    "data_privacy_concern",     
    "contradiction",            
]

#---------------------------------------------------------------------------
#QA prompt
#---------------------------------------------------------------------------
QA_SYSTEM_PROMPT = """
You are a meticulous QA analyst evaluating a medical office AI phone agent.
Your job is to read a call transcript and identify bugs, errors, and quality
issues in the AI AGENT's responses. The "patient" is a test bot so focus only
on what the AGENT does wrong or could do better.

Here are bug categories to look for:
- scheduling_error: Agent books/confirms appointments that are impossible
  (wrong day, closed hours, past dates, conflicting slots)
- incorrect_information: Agent provides wrong facts about office hours,
  location, accepted insurance, services offered
- hallucination: Agent claims capabilities or knowledge it cannot have
- failed_to_clarify: Agent should have asked for clarification but assumed
- premature_confirmation: Agent confirmed an action before completing it
- no_answer: Agent ignored a direct question from the patient
- inappropriate_response: Response is off-topic or doesn't address the need
- poor_ux: Overly long, confusing, repetitive, or robotic responses
- data_privacy_concern: Agent asked for unnecessary sensitive information
- contradiction: Agent contradicted itself within the same call

Here are severity levels:
- critical: Causes real patient harm (wrong medication info, dangerous advice)
- high: Breaks core functionality (wrong appointment, wrong info given as fact)
- medium: Degrades experience (confusing, no answer to question)
- low: Minor UX issue (slightly too long, slightly awkward phrasing)

IMPORTANT RULES:
1. Only flag real bugs, not stylistic preferences
2. The patient is a TEST BOT so do not flag the patient's behavior as bugs
3. Be specific: always include the exact agent quote
4. If there are no bugs, return an empty list, do not invent issues
5. Return ONLY valid JSON, no other text

Return a JSON array of bug objects. Each object must have exactly these fields:
{
  "severity": "critical|high|medium|low",
  "category": "<one of the categories above>",
  "description": "<clear explanation of the problem>",
  "agent_quote": "<the exact problematic agent utterance>",
  "expected_behavior": "<what the agent should have done>",
  "transcript_location": "<early|mid-call|end or time estimate>"
}

If no bugs are found, return: []
""".strip()

#Analyzing a call transcript for bugs
class BugAnalyzer:
    def __init__(self):
        #self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", "test-key"))

    async def analyze(self, transcript_path: Path) -> list[Bug]:
        transcript_text = self._load_transcript(transcript_path)
        if not transcript_text:
            logger.warning(f"Empty or missing transcript: {transcript_path}")
            return []

        logger.info(f"Analyzing transcript: {transcript_path.name}")
        bugs = await self._run_analysis(transcript_text)

        #Save per-call bug report alongside the transcript
        self._save_bug_report(
            bugs=bugs,
            transcript_path=transcript_path,
        )
        return bugs

    #Loading the transcript JSON and formatting it as a readable dialogue for the LLM.
    def _load_transcript(self, path: Path) -> Optional[str]:
        try:
            with open(path) as f:
                data = json.load(f)

            turns = data.get("turns", [])
            if not turns:
                return None

            # Format as a readable dialogue
            lines = [f"CALL TRANSCRIPT - {data.get('call_sid', 'unknown')}\n"]
            for i, turn in enumerate(turns, 1):
                speaker = turn["speaker"].upper()
                text = turn["text"]
                lines.append(f"[{i}] {speaker}: {text}")
            return "\n".join(lines)

        except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
            logger.error(f"Failed to load transcript {path}: {e}")
            return None
    #sending the formatted transcript to GPT-4o for analysis and parsing
    async def _run_analysis(self, transcript_text: str) -> list[Bug]:
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": QA_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Please analyze this transcript for bugs:\n\n"
                            f"{transcript_text}"
                        ),
                    },
                ],
                temperature=0.1,   
                max_tokens=2000,  
                response_format={"type": "json_object"},
            )

            raw_json = response.choices[0].message.content
            return self._parse_bugs(raw_json)

        except Exception as e:
            logger.error(f"Bug analysis API call failed: {e}", exc_info=True)
            return []

    #Parsing the LLM's JSON response into Bug objects, handling both array and object formats.
    def _parse_bugs(self, raw_json: str) -> list[Bug]:
        try:
            data = json.loads(raw_json)
            if isinstance(data, dict):
                bug_list = data.get("bugs", data.get("issues", []))
            elif isinstance(data, list):
                bug_list = data
            else:
                logger.warning(f"Unexpected JSON format from analyzer: {type(data)}")
                return []

            bugs = []
            for item in bug_list:
                if not isinstance(item, dict):
                    continue
                try:
                    bug = Bug(
                        severity=item.get("severity", "medium").lower(),
                        category=item.get("category", "unknown"),
                        description=item.get("description", ""),
                        agent_quote=item.get("agent_quote", ""),
                        expected_behavior=item.get("expected_behavior", ""),
                        transcript_location=item.get("transcript_location", "unknown"),
                    )
                    bugs.append(bug)
                except (KeyError, TypeError) as e:
                    logger.warning(f"Skipping malformed bug entry: {e}")

            return bugs

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse bug analysis JSON: {e}")
            logger.debug(f"Raw response: {raw_json[:500]}")
            return []
    #Saving the identified bugs in both JSON and Markdown formats
    def _save_bug_report(self, bugs: list[Bug], transcript_path: Path) -> None:
        call_sid = transcript_path.stem  
        report_dir = Path("reports")
        report_dir.mkdir(exist_ok=True)

        #json format for structured data and potential future processing
        json_path = report_dir / f"bugs_{call_sid}.json"
        with open(json_path, "w") as f:
            json.dump(
                [b.to_dict() for b in bugs],
                f,
                indent=2,
            )

        #Markdown format 
        md_path = report_dir / f"bugs_{call_sid}.md"
        with open(md_path, "w") as f:
            f.write(f"# Bug Report — Call {call_sid}\n\n")
            f.write(f"**Transcript:** `transcripts/{call_sid}.json`\n\n")
            f.write(f"**Bugs found:** {len(bugs)}\n\n")

            if not bugs:
                f.write("No bugs found in this call.\n")
            else:
                #Grouping by severity
                for severity in ("critical", "high", "medium", "low"):
                    severity_bugs = [b for b in bugs if b.severity == severity]
                    if severity_bugs:
                        f.write(f"## {severity.upper()} Severity\n\n")
                        for bug in severity_bugs:
                            f.write(bug.to_markdown())
                            f.write("\n---\n\n")

        logger.info(f"Bug report saved: {md_path} ({len(bugs)} bugs)")
