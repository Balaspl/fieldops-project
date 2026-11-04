"""
sentiment_engine.py

Sentiment Analysis Engine for FieldOps Commander.

Responsibilities
----------------
- Analyze customer communication.
- Identify overall sentiment.
- Return a validated SentimentDecision.
- Provide keyword fallback when the AI provider is unavailable.

The Sentiment Engine does NOT:
- Generate customer replies.
- Assign technicians.
- Dispatch jobs.
- Modify database records.
- Send notifications.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

from app.services.ai.FieldOpsAI.runtime.orchestrator import (
    AIOrchestrator,
    ai_orchestrator,
)
from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
from app.services.ai.FieldOpsAI.schemas.sentiment import (
    SentimentContext,
    SentimentDecision,
)

logger = logging.getLogger(__name__)


class SentimentEngine:
    """
    AI engine responsible for customer sentiment analysis.
    """

    def __init__(
        self,
        orchestrator: Optional[AIOrchestrator] = None,
    ) -> None:
        self.orchestrator = orchestrator or ai_orchestrator

    # ---------------------------------------------------------
    # Keyword fallback
    # ---------------------------------------------------------

    def _keyword_fallback(
        self,
        context: SentimentContext,
    ) -> SentimentDecision:
        """
        Detect sentiment using keyword rules when the AI
        provider is unavailable.

        Supports:
        - English
        - Spanish
        - Tamil
        - Hindi
        """

        message = context.message.lower().strip()

        # -----------------------------------------------------
        # Positive keywords
        # -----------------------------------------------------

        positive_words = (
            # English
            "good",
            "great",
            "excellent",
            "amazing",
            "happy",
            "satisfied",
            "thank you",
            "thanks",
            "appreciate",
            "helpful",
            "perfect",
            "wonderful",
            "fixed the issue",
            "resolved the issue",
            "problem solved",
            "worked well",

            # Spanish
            "bueno",
            "buena",
            "excelente",
            "genial",
            "feliz",
            "satisfecho",
            "satisfecha",
            "gracias",
            "agradecido",
            "agradecida",
            "perfecto",
            "perfecta",

            # Tamil
            "நன்றி",
            "மிகவும் நன்றி",
            "நல்ல",
            "சிறந்த",
            "அருமை",
            "மகிழ்ச்சி",
            "திருப்தி",

            # Hindi
            "धन्यवाद",
            "बहुत अच्छा",
            "अच्छा",
            "अच्छी",
            "शानदार",
            "बेहतरीन",
            "खुश",
            "संतुष्ट",
        )

        # -----------------------------------------------------
        # Negative keywords
        # -----------------------------------------------------

        negative_words = (
            # English
            "bad",
            "terrible",
            "awful",
            "angry",
            "unhappy",
            "dissatisfied",
            "frustrated",
            "disappointed",
            "hate",
            "problem",
            "complaint",
            "broken",
            "failed",
            "not working",
            "worst",
            "poor",
            "late",
            "nobody told me",
            "no one told me",
            "wasn't informed",
            "was not informed",

            # Spanish
            "malo",
            "mala",
            "terrible",
            "horrible",
            "enojado",
            "enojada",
            "insatisfecho",
            "insatisfecha",
            "frustrado",
            "frustrada",
            "decepcionado",
            "decepcionada",
            "problema",
            "queja",
            "roto",
            "no funciona",
            "peor",

            # Tamil
            "மோசம்",
            "மோசமான",
            "கோபம்",
            "வருத்தம்",
            "ஏமாற்றம்",
            "பிரச்சனை",
            "புகார்",
            "வேலை செய்யவில்லை",
            "சரி இல்லை",
            "திருப்தி இல்லை",

            # Hindi
            "बुरा",
            "बुरी",
            "खराब",
            "भयानक",
            "गुस्सा",
            "नाराज़",
            "असंतुष्ट",
            "निराश",
            "समस्या",
            "शिकायत",
            "काम नहीं कर रहा",
            "सबसे खराब",
        )

        # -----------------------------------------------------
        # Intensifiers
        # -----------------------------------------------------

        intensifiers = (
            # English
            "very",
            "really",
            "extremely",
            "so",
            "highly",
            "absolutely",

            # Spanish
            "muy",
            "realmente",
            "extremadamente",
            "absolutamente",

            # Tamil
            "மிகவும்",
            "ரொம்ப",
            "மிக",

            # Hindi
            "बहुत",
            "बेहद",
            "अत्यंत",
            "बहुत ज्यादा",
        )

        positive_score = 0.0
        negative_score = 0.0

        # -----------------------------------------------------
        # Calculate positive score
        # -----------------------------------------------------

        for word in positive_words:
            if word in message:
                positive_score += 1.0

                if any(
                    f"{intensifier} {word}" in message
                    for intensifier in intensifiers
                ):
                    positive_score += 0.5

        # -----------------------------------------------------
        # Calculate negative score
        # -----------------------------------------------------

        for word in negative_words:
            if word in message:
                negative_score += 1.0

                if any(
                    f"{intensifier} {word}" in message
                    for intensifier in intensifiers
                ):
                    negative_score += 0.5

        # Use an explicitly supplied feedback rating as supporting signal.
        # A middle rating stays neutral and does not override the written comment.
        rating_match = re.search(r"customer rating:\s*([1-5])\s*/\s*5", message)
        if rating_match:
            rating = int(rating_match.group(1))
            if rating <= 2:
                negative_score += 1.0
            elif rating >= 4:
                positive_score += 1.0

        # -----------------------------------------------------
        # Determine sentiment
        # -----------------------------------------------------

        if positive_score > 0 and negative_score > 0:
            sentiment = "MIXED"

            confidence = min(
                0.95,
                0.70
                + min(
                    positive_score,
                    negative_score,
                )
                * 0.08,
            )

        elif positive_score > 0:
            sentiment = "POSITIVE"

            confidence = min(
                0.95,
                0.70 + positive_score * 0.08,
            )

        elif negative_score > 0:
            sentiment = "NEGATIVE"

            confidence = min(
                0.95,
                0.70 + negative_score * 0.08,
            )

        else:
            sentiment = "NEUTRAL"
            confidence = 0.50

        confidence = round(confidence, 2)

        # -----------------------------------------------------
        # Determine emotion
        # -----------------------------------------------------

        anger_words = (
            "angry",
            "enojado",
            "enojada",
            "கோபம்",
            "गुस्सा",
            "नाराज़",
        )

        disappointment_words = (
            "disappointed",
            "decepcionado",
            "decepcionada",
            "ஏமாற்றம்",
            "निराश",
        )

        if sentiment == "POSITIVE":
            emotion = "HAPPY"

        elif sentiment == "NEGATIVE":
            if any(
                word in message
                for word in anger_words
            ):
                emotion = "ANGRY"

            elif any(
                word in message
                for word in disappointment_words
            ):
                emotion = "DISAPPOINTED"

            else:
                emotion = "FRUSTRATED"

        elif sentiment == "MIXED":
            emotion = "CONCERNED"

        else:
            emotion = "CALM"

        # -----------------------------------------------------
        # Determine urgency
        # -----------------------------------------------------

        high_urgency_keywords = (
            # English
            "safety",
            "danger",
            "emergency",
            "manager",
            "supervisor",
            "escalate",
            "escalation",
            "cancel",
            "cancellation",
            "broken",
            "not working",
            "still not fixed",
            "multiple complaints",

            # Spanish
            "seguridad",
            "emergencia",
            "gerente",
            "supervisor",
            "escalar",
            "cancelar",
            "no funciona",

            # Tamil
            "பாதுகாப்பு",
            "அவசரம்",
            "மேலாளர்",
            "புகார்",
            "ரத்து",
            "வேலை செய்யவில்லை",

            # Hindi
            "सुरक्षा",
            "आपातकाल",
            "मैनेजर",
            "प्रबंधक",
            "एस्केलेट",
            "रद्द",
            "काम नहीं कर रहा",
        )

        medium_urgency_keywords = (
            "problem",
            "issue",
            "complaint",
            "frustrated",
            "disappointed",
            "problema",
            "queja",
            "பிரச்சனை",
            "புகார்",
            "समस्या",
            "शिकायत",
        )

        critical_urgency_keywords = (
            "immediate danger", "life threatening", "electric shock", "fire",
            "unsafe", "emergency", "peligro inmediato", "emergencia",
            "மின்சார அதிர்ச்சி", "அவசரம்", "तत्काल खतरा", "आपातकाल",
        )

        if any(keyword in message for keyword in critical_urgency_keywords):
            urgency = "CRITICAL"

        elif any(
            keyword in message
            for keyword in high_urgency_keywords
        ):
            urgency = "HIGH"

        elif any(
            keyword in message
            for keyword in medium_urgency_keywords
        ):
            urgency = "MEDIUM"

        else:
            urgency = "LOW"

        # -----------------------------------------------------
        # Determine human intervention
        # -----------------------------------------------------

        human_intervention_keywords = (
            "manager",
            "supervisor",
            "escalate",
            "escalation",
            "legal",
            "lawyer",
            "safety",
            "danger",
            "emergency",

            "gerente",
            "supervisor",
            "escalar",

            "மேலாளர்",
            "பாதுகாப்பு",
            "அவசரம்",

            "मैनेजर",
            "सुरक्षा",
            "आपातकाल",
        )

        requires_human = (
            any(
                keyword in message
                for keyword in human_intervention_keywords
            )
            or emotion == "ANGRY"
            or (
                sentiment == "NEGATIVE"
                and confidence < 0.70
            )
        )

        # -----------------------------------------------------
        # Factual summary
        # -----------------------------------------------------

        if sentiment == "POSITIVE":
            summary = (
                "Customer expresses positive feedback "
                "about the service."
            )

        elif sentiment == "NEGATIVE":
            summary = (
                "Customer expresses dissatisfaction "
                "or reports a service problem."
            )

        elif sentiment == "MIXED":
            summary = (
                "Customer expresses both positive and "
                "negative feelings about the service."
            )

        else:
            summary = (
                "Customer provides factual or emotionally "
                "neutral information."
            )

        return SentimentDecision(
            sentiment=sentiment,
            emotion=emotion,
            urgency=urgency,
            severity=(
                "CRITICAL"
                if any(word in message for word in ("safety", "danger", "emergency", "seguridad", "emergencia", "பாதுகாப்பு", "அவசரம்", "सुरक्षा", "आपातकाल"))
                else "HIGH" if any(word in message for word in ("third time", "multiple unresolved", "injured", "injury", "unsafe"))
                else "MEDIUM" if sentiment in {"NEGATIVE", "MIXED"}
                else "LOW"
            ),
            issue_categories=self._classify_issue_categories(message),
            requires_human=requires_human,
            confidence=confidence,
            summary=summary,
            recommended_action=(
                "Review the customer's message and contact them with an update."
                if sentiment in {"NEGATIVE", "MIXED"} or requires_human
                else "No follow-up is indicated by this message."
            ),
        )

    @staticmethod
    def _classify_issue_categories(message: str) -> list[str]:
        categories = []
        rules = (
            ("TECHNICIAN_DELAY", ("late", "waiting", "not arrived", "delay")),
            ("COMMUNICATION", ("no response", "not responding", "nobody is responding", "no update", "nobody told me", "no one told me", "wasn't informed", "was not informed")),
            ("SERVICE_QUALITY", ("poor service", "bad service", "did not fix", "not fixed")),
            ("SCHEDULING", ("appointment", "reschedule", "schedule")),
            ("PRICING_BILLING", ("price", "bill", "charge", "cost")),
            ("UNRESOLVED_ISSUE", ("again", "still broken", "still not", "unresolved")),
            ("SAFETY", ("safety", "danger", "unsafe", "emergency")),
        )
        for category, terms in rules:
            if any(term in message for term in terms):
                categories.append(category)
        if not categories and any(term in message for term in ("great", "thanks", "thank you", "excellent", "customer rating:")):
            categories.append("GENERAL_FEEDBACK")
        return categories[:5]

    # ---------------------------------------------------------
    # Main analysis
    # ---------------------------------------------------------

    def analyze(
        self,
        context: SentimentContext,
    ) -> SentimentDecision:
        """
        Analyze customer communication using the AI
        orchestrator with keyword fallback.
        """

        start_time = time.perf_counter()

        logger.info(
            "Sentiment Engine started."
        )

        try:
            # -------------------------------------------------
            # Primary path: AI through orchestrator
            # -------------------------------------------------

            decision = self.orchestrator.execute(
                task=AITask.SENTIMENT,
                context=context.model_dump(),
                response_schema=SentimentDecision,
            )

            elapsed = time.perf_counter() - start_time

            logger.info(
                "Sentiment completed in %.2f sec | "
                "Sentiment=%s | Confidence=%.2f",
                elapsed,
                decision.sentiment,
                decision.confidence,
            )

            return decision

        except Exception as exc:
            # -------------------------------------------------
            # Fallback path
            # -------------------------------------------------

            logger.exception(
                "AI sentiment analysis failed. "
                "Using keyword fallback. Error=%s",
                exc,
            )

            fallback_result = self._keyword_fallback(
                context
            )

            logger.info(
                "Sentiment keyword fallback completed. "
                "Sentiment=%s | Confidence=%.2f",
                fallback_result.sentiment,
                fallback_result.confidence,
            )

            return fallback_result
