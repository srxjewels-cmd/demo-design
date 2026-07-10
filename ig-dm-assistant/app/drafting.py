"""Draft generation with Claude, plus sensitive-topic flagging."""

import json
import logging
import re
from pathlib import Path

import anthropic

from . import config, db

log = logging.getLogger("drafting")

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Keyword heuristics that always force the ⚠️ flag regardless of what Claude says.
SENSITIVE_PATTERNS = [
    (re.compile(r"\b(refund|money back|charge ?back|dispute)\b", re.I), "refund request"),
    (re.compile(r"\b(lawyer|legal|sue|court|report you)\b", re.I), "legal threat"),
    (re.compile(r"\b(angry|furious|scam|fraud|terrible|worst|never again|disgust)\b", re.I),
     "upset customer"),
    (re.compile(r"\b(broken|damaged|missing|never arrived|lost package)\b", re.I),
     "order problem"),
]
MONEY_RE = re.compile(r"(?:\$|₹|€|£|rs\.?\s*)(\d[\d,]*(?:\.\d+)?)", re.I)


def _read(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def build_system_prompt() -> str:
    """Business info + policies + dialect examples, assembled from prompts/."""
    sections = [
        "You draft Instagram DM replies on behalf of the business owner. "
        "You write AS the owner, in their voice and dialect. "
        "Rules:\n"
        "- Reply text only. No preamble, no quotes, no explanations.\n"
        "- Keep replies under ~500 characters unless the question truly needs more.\n"
        "- NEVER promise refunds, discounts, or delivery dates unless that exact "
        "information appears in the order data provided.\n"
        "- If you are unsure, or the customer is upset, keep the reply cautious and "
        "set the flag (see output format).\n",
        "## Business information & policies\n" + (_read("business_faq.md")
                                                  or "(not provided yet)"),
        "## Dialect & tone — real replies written by the owner\n"
        "Match this voice exactly:\n" + (_read("examples.md") or "(not provided yet)"),
        "## Output format\n"
        "Return ONLY a JSON object, no markdown fences:\n"
        '{"reply": "<the reply text>", "flag": <true|false>, '
        '"flag_reason": "<short reason or null>"}\n'
        "Set flag=true for refunds, complaints, angry customers, legal topics, or "
        "anything you are not confident about.",
    ]
    edits = db.edited_examples(limit=5)
    if edits:
        lines = ["## Recent owner corrections (prefer the corrected style)"]
        for e in edits:
            lines.append(f"Customer: {e['customer_message']}\n"
                         f"Draft (rejected): {e['draft_text']}\n"
                         f"Owner's version: {e['final_text']}")
        sections.append("\n\n".join(lines))
    return "\n\n".join(sections)


def heuristic_flags(customer_text: str) -> str | None:
    reasons = [reason for pattern, reason in SENSITIVE_PATTERNS
               if pattern.search(customer_text)]
    for amount in MONEY_RE.findall(customer_text):
        try:
            if float(amount.replace(",", "")) >= config.SENSITIVE_REFUND_THRESHOLD:
                reasons.append("large amount mentioned")
                break
        except ValueError:
            pass
    return ", ".join(dict.fromkeys(reasons)) or None


def _parse_response(raw: str) -> tuple[str, bool, str | None]:
    """Parse Claude's JSON; fall back to using the raw text as the reply."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        data = json.loads(text)
        return (str(data.get("reply", "")).strip(),
                bool(data.get("flag")),
                data.get("flag_reason"))
    except (json.JSONDecodeError, AttributeError):
        return text, False, None


async def generate_draft(sender_id: str, customer_text: str, profile: dict,
                         crm_summary: str) -> tuple[str, bool, str | None]:
    """Returns (draft_text, flagged, flag_reason)."""
    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

    thread = db.recent_messages(sender_id, limit=10)
    thread_lines = [
        ("Customer" if m["direction"] == "in" else "You") + ": " + m["text"]
        for m in thread
    ]

    context = {
        "crm_summary": crm_summary,
        "customer_profile": profile,
    }
    user_prompt = (
        "## Customer context\n"
        + json.dumps(context, indent=2, default=str)
        + "\n\n## Conversation so far\n"
        + ("\n".join(thread_lines) or f"Customer: {customer_text}")
        + "\n\nDraft the reply to the customer's latest message."
    )

    response = await client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=1024,
        system=[{
            "type": "text",
            "text": build_system_prompt(),
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = "".join(block.text for block in response.content if block.type == "text")
    reply, flagged, flag_reason = _parse_response(raw)

    heuristic = heuristic_flags(customer_text)
    if heuristic:
        flagged = True
        flag_reason = f"{flag_reason}; {heuristic}" if flag_reason else heuristic

    if not reply:
        reply = "(Claude returned an empty draft — write your own reply.)"
        flagged, flag_reason = True, "empty draft"
    return reply, flagged, flag_reason
