from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List

from openai import OpenAI


def axel_generate(
    tool: str,
    inputs: Dict[str, Any],
    tone: str = "confident",
    audience: str = "small business",
    brand: str = "RAR AI Studio",
) -> str:
    """
    Single interface used by app/main.py
    """
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return "ERROR: OPENAI_API_KEY is not set."

    client = OpenAI(api_key=api_key)

    tool = (tool or "").strip().lower()
    if tool == "marketing_pack":
        return _gen_marketing_pack(client, inputs, tone=tone, audience=audience, brand=brand)
    if tool == "sales_replies":
        return _gen_sales_replies(client, inputs, tone=tone, audience=audience, brand=brand)
    if tool == "funnel_html":
        return _gen_funnel_html(client, inputs, tone=tone, audience=audience, brand=brand)
    if tool == "salesperson_chat":
        return _gen_salesperson_chat(client, inputs, tone=tone, audience=audience, brand=brand)
    if tool == "sales_playbook":
        return _gen_sales_playbook(client, inputs, tone=tone, audience=audience, brand=brand)

    return f"ERROR: Unknown tool '{tool}'"


def _model() -> str:
    return (os.getenv("RAR_MODEL") or "gpt-4.1-mini").strip()


def _call(client: OpenAI, prompt: str) -> str:
    resp = client.responses.create(
        model=_model(),
        input=prompt,
    )
    return (resp.output_text or "").strip()


def _gen_marketing_pack(client: OpenAI, inputs: Dict[str, Any], tone: str, audience: str, brand: str) -> str:
    bn = (inputs.get("business_name") or "").strip()
    bt = (inputs.get("business_type") or "").strip()
    offer = (inputs.get("offer") or "").strip()
    loc = (inputs.get("location") or "").strip()

    deliverables = inputs.get("deliverables") or [
        "Hooks (10)",
        "Captions (6)",
        "Ad Copy (3)",
        "DM Closer Script (1)",
        "Landing Page Outline (1)",
    ]

    prompt = f"""
You are a human marketer writing fast, modern, high-converting copy.
Do NOT sound like AI. No filler. No lectures. No overly long explanations.

Brand/tool: {brand}
Audience: {audience}
Tone: {tone}

Business name: {bn}
Business type: {bt}
Offer (optional): {offer or "(not provided)"}
Location (optional): {loc or "(not provided)"}

Deliverables to produce:
{chr(10).join(f"- {d}" for d in deliverables)}

Format EXACTLY like this:

TITLE
(one line)

HOOKS (10)
1) ...
...

CAPTIONS (6)
1) ...
...

AD COPY (3)
1) Primary text:
   Headline:
   CTA:

DM CLOSER SCRIPT
- You:
- Them:
- You:

LANDING PAGE OUTLINE
- Hero headline:
- Subhead:
- Bullets (3):
- CTA:
""".strip()
    return _call(client, prompt)


def _gen_sales_replies(client: OpenAI, inputs: Dict[str, Any], tone: str, audience: str, brand: str) -> str:
    customer_message = (inputs.get("customer_message") or "").strip()
    bt = (inputs.get("business_type") or "").strip()
    offer = (inputs.get("offer") or "").strip()
    loc = (inputs.get("location") or "").strip()
    goal = (inputs.get("goal") or "book").strip().lower()
    objection = (inputs.get("objection") or "").strip().lower()

    prompt = f"""
You are an expert DM closer for small businesses.
Write HUMAN replies for DMs/comments (no corporate tone, no AI vibe).
Short. Clear. Confident.

Message to respond to:
"{customer_message}"

Business type: {bt}
Offer (optional): {offer or "(not provided)"}
Location (optional): {loc or "(not specified)"}
Goal: {goal}
Objection hint (optional): {objection or "(auto-detect from message)"}

Return EXACTLY this format:

REPLY (send this)
FOLLOW-UP QUESTION (1 line)
SOFT CLOSE (1 line)
HARD CLOSE (1 line)

Rules:
- 1–2 lines per section max
- Ask only what you need next (zip, pics, size, date, link, etc.)
- Sound like a real person typing fast
""".strip()
    return _call(client, prompt)


def _gen_funnel_html(client: OpenAI, inputs: Dict[str, Any], tone: str, audience: str, brand: str) -> str:
    bn = (inputs.get("business_name") or "").strip()
    bt = (inputs.get("business_type") or "").strip()
    offer = (inputs.get("offer") or "").strip()
    loc = (inputs.get("location") or "").strip()

    prompt = f"""
Generate a SINGLE-FILE landing page (HTML only) for a small business.
Modern. Clean. Mobile-first. No external assets. No JS. Minimal inline CSS is ok.
Include a simple CTA section telling them to DM/text/email (generic wording).

Business name: {bn}
Business type: {bt}
Offer (optional): {offer or "(not provided)"}
Location (optional): {loc or "(not provided)"}

Output ONLY the HTML file content. No markdown fences.
""".strip()
    return _call(client, prompt)


def _gen_salesperson_chat(client: OpenAI, inputs: Dict[str, Any], tone: str, audience: str, brand: str) -> str:
    profile = inputs.get("profile") or {}
    lead = inputs.get("lead") or {}
    history = inputs.get("history") or []
    message = (inputs.get("message") or "").strip()
    learned_playbook = (inputs.get("learned_playbook") or "").strip()

    # Normalize history (list of {role, content})
    hist_lines: List[str] = []
    for m in history[-12:]:
        r = (m.get("role") or "").strip()
        c = (m.get("content") or "").strip()
        if r and c:
            hist_lines.append(f"{r}: {c}")
    hist_block = "\n".join(hist_lines).strip()

    prompt = f"""
You are an elite DM closer for a small business.
Write like a real person. Short sentences. No “As an AI…”. No emojis unless the user uses them first.

Brand: {brand}
Audience: {audience}
Tone: {tone}

Business profile:
- Name: {profile.get("biz_name","")}
- Type: {profile.get("biz_type","")}
- Offer: {profile.get("offer","")}
- Location: {profile.get("location","")}
- CTA preference: {profile.get("contact_method","dm")}

Lead context:
- Name: {lead.get("name","")}
- Contact: {lead.get("contact","")}
- Source: {lead.get("source","")}
- Stage: {lead.get("stage","New")}

If you have a playbook, follow it:
{learned_playbook if learned_playbook else "(no playbook yet)"}

Recent conversation:
{hist_block if hist_block else "(no prior messages)"}

User just said:
"{message}"

TASK:
Return ONE message to send back that:
- answers their question
- asks 1 key qualifier
- nudges toward booking/quote
- never claims you are human, never claims you did real-world actions

Keep it to 1–3 short lines.
""".strip()
    return _call(client, prompt)


def _gen_sales_playbook(client: OpenAI, inputs: Dict[str, Any], tone: str, audience: str, brand: str) -> str:
    events = inputs.get("events") or []
    # keep prompt small
    trimmed = events[:40]

    prompt = f"""
You are building a SALES PLAYBOOK for an AI DM closer.
Use ONLY the provided win/loss events to extract patterns.
No fluff. No generic advice.

Brand: {brand}
Audience: {audience}
Tone: {tone}

Events (most recent first):
{trimmed}

Write a compact playbook in this exact format:

DO MORE OF (wins)
- ...
DO LESS OF (losses)
- ...
OBJECTION SNIPPETS
- Price: ...
- Trust: ...
- Timing: ...
QUALIFYING QUESTIONS (minimum)
- ...
CLOSES THAT WORK
- ...

Constraints:
- 250–450 words max
- concrete phrasing the AI can reuse
""".strip()
    return _call(client, prompt)
