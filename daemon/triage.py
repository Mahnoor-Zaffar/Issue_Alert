import asyncio
import logging
import re

from openai import AsyncOpenAI, RateLimitError, APITimeoutError, APIConnectionError

from config.settings import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a friendly coding teacher explaining a GitHub issue to someone who is just learning to code.

Rules:
- No jargon without explaining it in simple words right after
- Use analogies from real life (cooking, sports, school, building with LEGOs)
- **Use bullet points** instead of paragraphs — break everything into short bullet points
- Each bullet point max 2 lines
- Bold the most important word in each bullet point
- Start every section with one bullet that says what it means in plain English

Write exactly **four** sections with these exact headings:

## What This Part of the Code Does (Like I'm 10)
## What's Wrong and What Needs to Change
## Step-by-Step Plan to Fix It
## One-Line Fix

The **One-Line Fix** section must be a single sentence that says what the fix is in the simplest possible language, like you're telling a friend what needs to happen. Keep it as one short line — no bullet points here."""


SECTION_PATTERN = re.compile(
    r"##\s*What This Part of the Code Does \(Like I'm 10\)\s*\n(.*?)"
    r"##\s*What's Wrong and What Needs to Change\s*\n(.*?)"
    r"##\s*Step-by-Step Plan to Fix It\s*\n(.*?)"
    r"##\s*One-Line Fix\s*\n(.*)",
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
    ) -> dict[str, str]:
        user_message = self._build_user_message(
            title, body, labels, language, repo_url, file_context
        )

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

        if file_context:
            parts.append("\n## Repository File Context")
            for fc in file_context:
                parts.append(f"\n### {fc['path']}\n```\n{fc['content']}\n```")
        else:
            parts.append(
                "\n## Repository File Context\n(No file context available — clone failed or repo is empty.)"
            )

        return "\n".join(parts)

    def _parse_response(self, raw: str) -> dict[str, str]:
        match = SECTION_PATTERN.search(raw)
        if match:
            return {
                "architecture_context": match.group(1).strip(),
                "issue_breakdown": match.group(2).strip(),
                "action_plan": match.group(3).strip()
                + "\n\n**One-Line Fix:**\n"
                + match.group(4).strip(),
                "raw_response": raw,
            }

        logger.warning("Could not parse LLM response into sections, storing raw")
        return {
            "architecture_context": raw,
            "issue_breakdown": "",
            "action_plan": "",
            "raw_response": raw,
        }
