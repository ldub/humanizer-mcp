"""Copy schema, chunk planning, and conservative validation of candidate rewrites."""

import hashlib
import json
import re
from collections import Counter
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .vendor import hz_text as text_utils

PF = json.loads(files("humanizer_mcp").joinpath("prompt_format.json").read_text())


def build_prompt(text: str) -> str:
    return PF["instr"] + "\n\n" + text.strip() + PF["sep"]


if hashlib.sha256(build_prompt("X").encode()).hexdigest()[:16] != "cc51d66b4c593fbe":
    raise RuntimeError("The Humanizer prompt has changed; check the pinned model format")


class CopyField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=60_000)
    format: Literal["plain", "markdown"] = "plain"
    preserve: list[str] = Field(default_factory=list, max_length=100)
    max_characters: int | None = Field(default=None, ge=1, le=60_000)

    @model_validator(mode="after")
    def check_preserve(self):
        if any(not term or term not in self.text for term in self.preserve):
            raise ValueError("Each preserve term must be nonempty and appear in this field")
        return self


class RewriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[CopyField] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def check_size(self):
        if len({field.id for field in self.fields}) != len(self.fields):
            raise ValueError("Field ids must be unique")
        if sum(len(field.text) for field in self.fields) > 100_000:
            raise ValueError("Split batches larger than 100,000 characters")
        return self


# Preserve literal inline code, full Markdown links, URLs, placeholders, and quotations.
PROTECTED = re.compile(
    r"(`+)[^`\n]+?\1|!?\[[^\]\n]*\]\([^\n]*?\)|https?://[^\s<>]+|"
    r"\{\{[^{}]+\}\}|\$\{[^{}]+\}|\{[A-Za-z_][\w.]*\}|%\([^)]+\)[sd]|"
    r'"[^"\n]+"|“[^”\n]+”'
)
NUMBER = re.compile(r"(?<!\w)[+-]?\d+(?:[,.]\d+)*(?:\s*%|\s*(?:ms|GB|MB|KB|kg|km)\b)?")


def protected(text: str) -> Counter:
    return Counter(match.group(0) for match in PROTECTED.finditer(text))


def validate(original: str, candidate: str, *, preserve=(), truncated=False) -> list[str]:
    issues = []
    if not candidate.strip():
        issues.append("empty_output")
    if truncated:
        issues.append("truncated")
    if Counter(NUMBER.findall(original)) != Counter(NUMBER.findall(candidate)):
        issues.append("numbers_changed")
    if protected(original) != protected(candidate):
        issues.append("protected_content_changed")
    if any(original.count(term) != candidate.count(term) for term in preserve):
        issues.append("required_terms_changed")
    if text_utils.language_drift(original, candidate):
        issues.append("language_changed")
    if text_utils.stray_markup(original, candidate):
        issues.append("unexpected_markup")
    return issues


def rewrite_field(field: CopyField, generate) -> dict:
    """Return a candidate only if mechanical checks pass; never claim semantic validation."""
    if field.format == "markdown":
        plan = text_utils.plan_text(field.text, max_words=300, max_cjk=600, min_prose=1, min_item=1)
        units = [(unit.id, unit.text) for unit in plan.units]
        render = plan.render
    else:
        chunks = text_utils.cut_long(field.text.strip(), text_utils.Sizer(300, 600))
        units = list(enumerate(chunks))

        def render(results):
            return "\n\n".join(results[key] for key, _ in units)

    results, warnings = {}, []
    tokens = 0
    for key, draft in units:
        output = generate(draft)
        candidate = output["text"].strip()
        tokens += output.get("tokens", 0)
        issues = validate(
            draft,
            candidate,
            preserve=[t for t in field.preserve if t in draft],
            truncated=output.get("truncated", False),
        )
        if issues:
            warnings.extend(issues)
        results[key] = candidate
    candidate = render(results) if units else field.text
    warnings.extend(validate(field.text, candidate, preserve=field.preserve))
    if field.max_characters is not None and len(candidate) > field.max_characters:
        warnings.append("character_limit_exceeded")
    if not units:
        warnings.append("no_prose_to_rewrite")
    accepted = not warnings
    return {
        "id": field.id,
        "text": candidate if accepted else field.text,
        "status": "rewritten" if accepted else "original_retained",
        "warnings": sorted(set(warnings)),
        "characters": len(candidate if accepted else field.text),
        "generated_tokens": tokens,
        "review_required": accepted,
    }


def unchanged(request: RewriteRequest, status: str, message: str) -> dict:
    return {
        "status": status,
        "message": message,
        "fields": [
            {
                "id": f.id,
                "text": f.text,
                "status": "original_retained",
                "warnings": [status],
                "review_required": False,
            }
            for f in request.fields
        ],
    }
