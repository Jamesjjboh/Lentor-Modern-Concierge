"""Gemini 3.8 Flash Agent core & Toolbelt for Lentor Modern Concierge."""

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from google import genai
from google.genai import types

from src.config import GEMINI_API_KEY, GEMINI_MODEL, PROCESSED_DATA_DIR
from src.database import db_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# System instructions setting identity, guardrails, and tone
SYSTEM_INSTRUCTION = """
You are the Lentor Modern Digital Concierge, a helpful, polite, and accurate virtual concierge for the ~605 households of Lentor Modern (a premier integrated mixed-use development by GuocoLand in Singapore, atop Lentor Modern Mall and Lentor MRT).

You have access to 5 specialized tools:
1. `search_bylaws_and_handbook`: Use to look up official MCST by-laws, renovation hours & deposits, facility booking rules, aircon ledge rules, moving & delivery bay procedures, and handover defect procedures.
2. `search_mall_directory`: Use to look up shops, supermarkets (CS Fresh), clinics, childcare, and eateries in Lentor Modern Mall, including floor levels (B1, L1) and operating hours.
3. `get_verified_community_tips`: Use to retrieve crowdsourced neighbour advice (e.g. delivery bay access, induction cooker lock quirks, aircon piping SWG requirements, evening grocery discounts).
4. `generate_mcst_email_draft`: Use when a resident needs to formally email the Managing Agent (MA) to report a defect, common property issue, or submit a request.
5. `submit_tip_to_moderation`: Use when a resident shares a new helpful tip, discovery, or advice that should be added to the community knowledge base.


Guidelines:
- Maintain a warm, helpful, and professional Singapore condo concierge tone.
- When answering questions about estate rules or mall shops, ALWAYS invoke the relevant tool to provide factual, up-to-date information. Do not invent bylaw clauses.
- NEVER request or reveal sensitive Personally Identifiable Information (PII) like unit numbers (#XX-YY), private resident names, or mobile numbers.
- If you cannot find an answer in the bylaws, mall directory, or community tips, honestly say you do not have that information yet and offer to submit a request or draft an inquiry to the Managing Agent.
"""


# --- Tool 1: Bylaws & Handbook Search ---
def search_bylaws_and_handbook(query: str) -> str:
    """Searches official Lentor Modern MCST by-laws, renovation guidelines, facility policies, and estate rules."""
    handbook_file = PROCESSED_DATA_DIR / "bylaws_handbook.json"
    if not handbook_file.exists():
        return "No handbook or bylaws data is currently available in the estate database."

    try:
        with open(handbook_file, "r", encoding="utf-8") as f:
            records: List[Dict[str, Any]] = json.load(f)
    except Exception as e:
        return f"Error loading handbook records: {e}"

    query_tokens = set(re.findall(r"\w+", query.lower()))
    scored_matches: List[Tuple[int, Dict[str, Any]]] = []

    for r in records:
        content_text = f"{r.get('topic', '')} {r.get('section', '')} {r.get('content', '')} {r.get('text', '')}".lower()
        score = sum(1 for token in query_tokens if token in content_text)
        if score > 0:
            scored_matches.append((score, r))

    scored_matches.sort(key=lambda x: x[0], reverse=True)
    top_matches = [m[1] for m in scored_matches[:3]]

    if not top_matches:
        return f"No official by-laws found matching '{query}'. Please check with the Concierge desk."

    results = []
    for m in top_matches:
        heading = m.get("section") or m.get("topic") or f"Page {m.get('page', '')}"
        body = m.get("content") or m.get("text", "")
        results.append(f"[{heading}]\n{body}")

    return "\n\n".join(results)


# --- Tool 2: Mall Directory Search ---
def search_mall_directory(category: str = "", shop_name: str = "") -> str:
    """Looks up Lentor Modern Mall tenant directory, floor levels (B1, L1), unit numbers, and operating hours."""
    mall_file = PROCESSED_DATA_DIR / "mall_directory.json"
    if not mall_file.exists():
        return "Mall directory is currently being updated."

    try:
        with open(mall_file, "r", encoding="utf-8") as f:
            tenants: List[Dict[str, Any]] = json.load(f)
    except Exception as e:
        return f"Error loading mall directory: {e}"

    search_term = f"{category} {shop_name}".strip().lower()
    matches = []

    for t in tenants:
        match_str = f"{t.get('name', '')} {t.get('category', '')} {t.get('description', '')}".lower()
        if not search_term or any(word in match_str for word in search_term.split()):
            matches.append(t)

    if not matches:
        return f"No shops found in Lentor Modern Mall matching '{search_term}'."

    results = []
    for m in matches[:4]:
        info = (
            f"🏪 {m.get('name')} ({m.get('category')})\n"
            f"📍 Floor/Unit: {m.get('floor')} #{m.get('unit')}\n"
            f"⏰ Hours: {m.get('opening_hours')}\n"
            f"ℹ️ {m.get('description', '')}"
        )
        if m.get("tips"):
            info += f"\n💡 Tip: {m.get('tips')}"
        results.append(info)

    return "\n\n".join(results)


# --- Tool 3: Verified Community Tips ---
def get_verified_community_tips(topic: str = "") -> str:
    """Retrieves verified tribal knowledge and practical tips crowdsourced from Lentor Modern residents."""
    tips = []
    # 1. Check local seed file
    tips_file = PROCESSED_DATA_DIR / "verified_community_tips.json"
    if tips_file.exists():
        try:
            with open(tips_file, "r", encoding="utf-8") as f:
                seed_tips = json.load(f)
                t_lower = topic.strip().lower()
                for st in seed_tips:
                    if not t_lower or t_lower in st.get("topic", "").lower() or t_lower in st.get("content", "").lower():
                        tips.append(f"• [{st.get('topic', 'general').capitalize()}] {st.get('content')}")
        except Exception as e:
            logger.error(f"Error reading seed tips: {e}")

    # 2. Check approved tips in Firestore
    try:
        db_tips = db_client.get_approved_tips(topic=topic, limit=5)
        for dt in db_tips:
            tips.append(f"• [{dt.get('topic', 'community').capitalize()}] {dt.get('content')}")
    except Exception as e:
        logger.error(f"Error fetching Firestore approved tips: {e}")

    if not tips:
        return f"No verified community tips found for '{topic}' yet."

    return "Verified Resident Tips:\n" + "\n".join(tips[:5])


# --- Tool 4: MCST Email Draft Generator ---
def generate_mcst_email_draft(issue_type: str, details: str, resident_name: str = "Resident") -> str:
    """Formats a professional, bylaw-referenced email draft ready to send to the Managing Agent (MA)."""
    subject = f"[Lentor Modern] Resident Inquiry / Feedback: {issue_type}"
    body = (
        f"Subject: {subject}\n\n"
        f"Dear Managing Agent / Estate Office,\n\n"
        f"I am writing as a resident of Lentor Modern regarding {issue_type}.\n\n"
        f"Details:\n{details}\n\n"
        f"In accordance with estate management guidelines, could you kindly advise on the next steps or arrange for necessary rectifications?\n\n"
        f"Thank you for your assistance and prompt attention.\n\n"
        f"Best regards,\n"
        f"{resident_name}\n"
        f"Lentor Modern Residential Unit: [Your Unit #]"
    )
    return body


# --- Tool 5: Tip Moderation Submission ---
def submit_tip_to_moderation(topic: str, tip_text: str, user_id: int = 0) -> str:
    """Submits a resident's practical tip or contractor discovery to the moderation queue for admin approval."""
    try:
        tip_id = db_client.submit_community_tip(user_id=user_id, topic=topic, content=tip_text)
        return (
            f"Thank you! Your tip about '{topic}' has been submitted to the moderation queue "
            f"(Reference ID: {tip_id}). Once approved by the admin, it will be visible to all neighbours!"
        )
    except Exception as e:
        return f"Failed to submit tip: {e}"


# Toolbelt registry
TOOL_FUNCTIONS: List[Callable[..., Any]] = [
    search_bylaws_and_handbook,
    search_mall_directory,
    get_verified_community_tips,
    generate_mcst_email_draft,
    submit_tip_to_moderation,
]


class LentorAgent:
    """Autonomous agent wrapping Gemini 3.8 Flash and the Lentor Modern tool catalog."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.model = model or GEMINI_MODEL
        self.client: Optional[genai.Client] = None
        self._init_client()

    def _init_client(self):
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            logger.info(f"Initialized Gemini Agent with model: {self.model}")
        else:
            logger.warning("GEMINI_API_KEY is not set. Agent will run in simulated rule-matching mode.")

    def run_query(self, user_query: str, user_id: int = 0) -> Tuple[str, List[str]]:
        """Processes a resident query, calls tools as needed, and returns (response_text, tools_called)."""
        tools_called: List[str] = []

        if not self.client:
            # Fallback simulator for local testing before API key is provided
            return self._simulated_response(user_query, user_id)

        candidate_models = [self.model]
        for fallback in ["gemini-3.5-flash", "gemini-3.1-flash-lite"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=TOOL_FUNCTIONS,
            temperature=0.3,
        )

        last_error = None
        for current_model in candidate_models:
            try:
                chat = self.client.chats.create(
                    model=current_model,
                    config=config,
                )

                response = chat.send_message(user_query)
                final_text = response.text or ""

                # Check history for tool calls executed by the agent
                for msg in chat.get_history():
                    for part in getattr(msg, "parts", []):
                        fn_call = getattr(part, "function_call", None)
                        if fn_call and fn_call.name:
                            tools_called.append(fn_call.name)

                return final_text, tools_called

            except Exception as e:
                if any(code in str(e) for code in ["503", "UNAVAILABLE", "402", "RESOURCE_EXHAUSTED", "429"]):
                    logger.warning(f"Model {current_model} error ({e}). Cascading to next fallback model...")
                    continue
                else:
                    logger.error(f"Error in Gemini agent query execution with {current_model}: {e}")
                    break


        return f"I encountered an unexpected issue processing your query: {last_error}. Please try again shortly.", tools_called

    def analyze_resident_image(
        self,
        image_bytes: bytes,
        caption: str = "",
        user_id: int = 0,
    ) -> Dict[str, Any]:
        """Analyzes an image and optional caption using Gemini Vision.
        Determines if it's a community tip submission or a visual query/troubleshooting.
        """
        if not self.client:
            return {
                "intent": "TIP_SUBMISSION" if "/tip" in caption.lower() else "RESIDENT_QUESTION",
                "topic": "general",
                "title": "Photo Discovery",
                "tip": caption or "Resident submitted photo tip.",
                "user_reply": "📸 Photo received! In live mode, Gemini 3.8 Flash will analyze the text and details.",
            }

        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

        prompt = f"""
You are the Lentor Modern Digital Concierge analyzing an image sent by a resident of Lentor Modern.
The resident included this caption: "{caption}".

Evaluate the resident's intent:
1. "TIP_SUBMISSION": The resident is sharing an informative poster, retail promotion, opening hours notice, or neighbour recommendation (or they explicitly included '/tip' in the caption).
2. "RESIDENT_QUESTION": The resident is asking a question about what is shown in the image (e.g. an appliance error code on their induction hob, where something is located, a defect, or estate rule).

If TIP_SUBMISSION:
- Extract the core details from the image and caption.
- Determine the topic: one of ["mall", "services", "appliances", "bylaws", "food", "general"].
- Title: A concise title (e.g., "CS Fresh Sushi Evening Discount", "Minmed Clinic Weekend Hours").
- Tip: Clear, actionable, and structured advice for neighbours (including store unit number, floor, timings, discount percentage).
- Ensure strict PII scrubbing: DO NOT include private resident names, unit numbers (#XX-YY), or phone numbers.
- Friendly reply confirming submission to moderation.

If RESIDENT_QUESTION:
- Inspect the visual details (e.g., error code 'L' on induction cooker, defect sticker, facility sign).
- Answer the resident's question directly, referencing known estate quirks (e.g. 'L' on induction hob = child lock; hold key for 3 seconds).

Return a JSON object with this exact structure:
{{
  "intent": "TIP_SUBMISSION" or "RESIDENT_QUESTION",
  "topic": "mall",
  "title": "Short Title",
  "tip": "Extracted tip content (empty if RESIDENT_QUESTION)",
  "user_reply": "Message to send to resident"
}}
"""

        candidate_models = [self.model]
        for fallback in ["gemini-3.5-flash", "gemini-3.1-flash-lite"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        config = types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
        )

        for current_model in candidate_models:
            try:
                response = self.client.models.generate_content(
                    model=current_model,
                    contents=[image_part, prompt],
                    config=config,
                )
                text = response.text or "{}"
                data = json.loads(text)
                return data
            except Exception as e:
                if any(code in str(e) for code in ["503", "UNAVAILABLE", "402", "RESOURCE_EXHAUSTED", "429"]):
                    logger.warning(f"Model {current_model} error ({e}) during image analysis. Cascading...")
                    continue
                else:
                    logger.error(f"Image analysis error with {current_model}: {e}")
                    break


        return {
            "intent": "RESIDENT_QUESTION",
            "topic": "general",
            "title": "Photo Analysis",
            "tip": "",
            "user_reply": "I received your photo but had trouble processing the details. Could you please try again or describe what is in the photo?",
        }



    def _simulated_response(self, user_query: str, user_id: int) -> Tuple[str, List[str]]:
        """Rule-based simulation mode for testing when Gemini API key is not yet set."""
        q_lower = user_query.lower()
        tools_called = []

        if any(w in q_lower for w in ["bylaw", "rule", "renovation", "deposit", "moving", "aircon ledge", "riser", "bbq", "gym", "hours", "parking"]):
            tools_called.append("search_bylaws_and_handbook")
            result = search_bylaws_and_handbook(user_query)
            return f"[Simulated Gemini 3.8 Flash Response]\n\nBased on official estate guidelines:\n\n{result}", tools_called

        elif any(w in q_lower for w in ["mall", "cs fresh", "supermarket", "clinic", "shop", "toast box", "mrt", "guardian"]):
            tools_called.append("search_mall_directory")
            result = search_mall_directory(shop_name=user_query)
            return f"[Simulated Gemini 3.8 Flash Response]\n\nFrom the Lentor Modern Mall directory:\n\n{result}", tools_called

        elif any(w in q_lower for w in ["tip", "advice", "hack", "trick", "discount"]):
            tools_called.append("get_verified_community_tips")
            result = get_verified_community_tips(topic=user_query)
            return f"[Simulated Gemini 3.8 Flash Response]\n\n{result}", tools_called

        elif any(w in q_lower for w in ["email", "draft", "ma", "managing agent", "complain", "feedback"]):
            tools_called.append("generate_mcst_email_draft")
            result = generate_mcst_email_draft(issue_type="Estate Feedback", details=user_query)
            return f"[Simulated Gemini 3.8 Flash Response]\n\nHere is a draft email for the Managing Agent:\n\n{result}", tools_called

        return (
            "[Simulated Gemini 3.8 Flash Response]\n\n"
            "Hello! I am the Lentor Modern AI Concierge. You can ask me about MCST by-laws, renovation hours, "
            "mall shops & opening hours, or verified neighbour tips. (Configure GEMINI_API_KEY to enable full live agent reasoning).",
            tools_called,
        )


# Global agent instance
concierge_agent = LentorAgent()
