import asyncio
import logging
import re

from openai import AsyncOpenAI, RateLimitError, APITimeoutError, APIConnectionError

from config.settings import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior open-source engineer performing issue triage.
Analyze the GitHub issue and repository context provided by the user.

Respond with EXACTLY three markdown sections using these exact headings:

## Codebase Architecture Context
Describe the likely architecture and relevant parts of the codebase based on the file context and issue.

## Core Issue Breakdown
Break down what the issue is asking for, key constraints, and potential complexity.

## Suggested PR Action Plan
Provide a concrete, step-by-step plan for implementing a pull request to address this issue.

Be precise and actionable. If file context is unavailable, infer from the issue description and repo name."""

SECTION_PATTERN = re.compile(
    r"##\s*Codebase Architecture Context\s*\n(.*?)"
    r"##\s*Core Issue Breakdown\s*\n(.*?)"
    r"##\s*Suggested PR Action Plan\s*\n(.*)",
    re.DOTALL | re.IGNORECASE,
)


class TriageEngine:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

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
                    model=settings.openai_model,
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
                    "OpenAI error (attempt %d): %s — retrying in %ds",
                    attempt + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError("OpenAI triage failed after 3 retries")

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
                "action_plan": match.group(3).strip(),
                "raw_response": raw,
            }

        logger.warning("Could not parse LLM response into sections, storing raw")
        return {
            "architecture_context": raw,
            "issue_breakdown": "",
            "action_plan": "",
            "raw_response": raw,
        }
