import asyncio
import json
import logging
import re

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError

from config.settings import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are an experienced open-source contributor performing issue triage for a GitHub repository.

Your task is to produce a concise, evidence-based triage report that can be posted publicly as a GitHub comment.


Investigation Process (Mandatory)


Before writing anything, perform the following steps:


Read the entire GitHub issue, including the title, body, comments, labels, screenshots,
stack traces, logs, and any attached files.
Read every linked pull request, discussion, commit, or external reference mentioned in the issue.
Search the repository for the code related to the reported problem.
Read the relevant implementation files before drawing any conclusions.
Read any relevant documentation or README sections if they affect the reported behavior.
Base every statement only on information that can be verified from:
the issue,
repository source code,
documentation,
linked discussions,
linked PRs.


Never invent facts.


If something cannot be verified, explicitly state that it requires confirmation instead of guessing.


Do not assume filenames, APIs, functions, classes, modules, or root causes unless they
can be confirmed from the repository.


Output Format


Write the report exactly in the following format.


Hey! Thanks for reporting this.


Understanding of the problem
Briefly explain what the issue is describing.
Describe the expected behavior.
Describe the observed behavior.
Mention important assumptions separately only if necessary.
Core problem


Identify the most likely root cause.


If the repository clearly identifies the affected code, naturally reference the relevant:


file(s)
function(s)
class(es)
module(s)


Do not force references if they cannot be verified.


If multiple causes are possible, list them in order of likelihood instead of pretending certainty.


Keep this section concise.


Suggested approach


Provide one or two sentences describing the most reasonable direction for fixing the issue.


Do not include implementation details.


Do not include code.


Clarifications

Include this section only if additional information is genuinely required.
Ask only the minimum number of questions needed to move the issue forward.
Omit this section entirely if nothing is missing.
Finish every report with exactly this sentence:
If no one is currently working on this, I'd be happy to take a look and put together a fix.

Writing Style


The report must read like it was written manually by an experienced maintainer or contributor.


Do not sound like an AI assistant.


Avoid phrases such as:


'Based on my analysis...'
'It appears that...'
'Here's my understanding...'
'I analyzed...'
'I hope this helps.'


Do not use emojis.


Do not use unnecessary formatting.


Avoid repetitive sentence openings.


Vary sentence structure naturally.


Keep the report concise.


Target length:


Normally under 250 words.
Longer only if the issue is unusually complex.


Never speculate.


Never hallucinate.


If evidence is insufficient, say so explicitly.
"""


SECTION_PATTERN = re.compile(
    r"##\s*(?:Understanding|🧩 What This Part of the Code Does)\s*\n(.*?)(?=##\s*|$)"
    r"##\s*(?:Core problem|🐛 What's Wrong and What Needs to Change)\s*\n(.*?)(?=##\s*|$)"
    r"##\s*(?:Suggested approach|📁 Files You'll Need to Edit|📝 Step-by-Step Plan)\s*\n(.*?)(?=##\s*|$)"
    r"(?:##\s*(?:Clarifications|💬|💡 One-Line Fix)\s*\n(.*?))?$",
    re.DOTALL | re.IGNORECASE,
)

VARIANT_RE = re.compile(
    r"(?:^|\n)\s*(?:VARIANT[_ ]?)?[A-C]:\s*(.*?)(?=\n\s*(?:VARIANT[_ ]?)?[A-C]:|\Z)",
    re.DOTALL | re.IGNORECASE,
)


class TriageEngine:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            default_headers={
                "HTTP-Referer": "https://github.com/Mahnoor-Zaffar/Issue_Alert",
                "X-Title": "GitHub Issue Triage",
            },
        )

    async def triage(
        self,
        title: str,
        body: str,
        labels: list[str],
        language: str | None,
        repo_url: str,
        file_context: list[dict[str, str]],
        file_paths: list[str] | None = None,
    ) -> dict[str, str]:
        user_message = self._build_user_message(title, body, labels, language, repo_url, file_context, file_paths)

        for attempt in range(3):
            try:
                response = await self._client.chat.completions.create(
                    model=settings.llm_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.3,
                    max_tokens=2000,
                )
                raw = response.choices[0].message.content or ""
                return self._parse_response(raw)

            except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
                delay = 2 ** (attempt + 1)
                logger.warning(
                    "LLM error (attempt %d): %s — retrying in %ds",
                    attempt + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError("LLM triage failed after 3 retries")

    def _build_user_message(
        self,
        title: str,
        body: str,
        labels: list[str],
        language: str | None,
        repo_url: str,
        file_context: list[dict[str, str]],
        file_paths: list[str] | None = None,
    ) -> str:
        parts = [
            f"# Issue: {title}",
            f"Repository: {repo_url}",
            f"Labels: {', '.join(labels) if labels else 'none'}",
            f"Language: {language or 'unknown'}",
            "",
            "## Issue Body",
            body or "(empty)",
        ]

        if file_paths:
            parts.append("\n## Repository source files (use ONLY these paths in 📁 Files section)")
            for fp in sorted(file_paths):
                parts.append(f"- `{fp}`")

        if file_context:
            parts.append("\n## Repository File Context")
            for fc in file_context:
                parts.append(f"\n### {fc['path']}\n```\n{fc['content']}\n```")
        else:
            parts.append("\n## Repository File Context\n(No file context available — clone failed or repo is empty.)")

        return "\n".join(parts)

    def _parse_response(self, raw: str) -> dict[str, str]:
        match = SECTION_PATTERN.search(raw)
        if match:
            return {
                "architecture_context": match.group(1).strip(),
                "issue_breakdown": match.group(2).strip(),
                "action_plan": match.group(3).strip(),
                "claim_comment": match.group(4).strip() if match.group(4) else "",
                "claim_variants": self._parse_variants(match.group(4) or ""),
                "raw_response": raw,
            }

        logger.warning("Could not parse LLM response into sections, storing raw")
        return {
            "architecture_context": "",
            "issue_breakdown": "",
            "action_plan": "",
            "claim_comment": json.dumps([raw]),
            "claim_variants": [raw],
            "raw_response": raw,
        }

    @staticmethod
    def _parse_variants(text: str) -> list[str]:
        matches = VARIANT_RE.findall(text)
        variants = [m.strip() for m in matches if m.strip()]
        if not variants and text.strip():
            variants = [text.strip()]
        return variants
