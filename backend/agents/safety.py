import re
from typing import Tuple, Optional


class SafetyPolicy:
    """
    Safety Policy & Guardrail Engine.
    Rules:
    - BLOCK facial recognition, biometric identification, and identity tracking.
    - BLOCK prompt injection, shell command execution, and code execution attempts.
    - FLAG weapon / physical security threats as 'requires_human_review'.
    """

    # Prohibited facial recognition & biometric tracking patterns
    FACIAL_PATTERNS = [
        r"\bfaces?\b",
        r"\bfacial(?:s)?\b",
        r"\bface\s*recognition\b",
        r"\bwho\s+is\s+this\b",
        r"\bidentify\s+(?:person|individual|people|user|faces?|suspect)\b",
        r"\bidentity\s*tracking\b",
        r"\btrack\s+(?:person\s+identity|identity)\b",
        r"\bbiometric(?:s)?\b",
        r"\baadhaar\b",
        r"\bchehr[aeo]\b",        # Hindi for face/faces
        r"\bpeh?chan\b",          # Hindi for identify
    ]

    # Prompt injection and jailbreak patterns
    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
        r"system\s*prompt",
        r"run\s+(shell|bash|powershell|cmd|sh)",
        r"execute\s+(code|script|command)",
        r"\brm\s+-rf\b",
        r"drop\s+table",
        r"you\s+are\s+now\s+(in\s+dan\s+mode|a\s+hacker|unrestricted)",
        r"bypass\s+(safety|rules|gate|guardrail)"
    ]

    # Threat / weapon surveillance (requires human supervisor review)
    THREAT_PATTERNS = [
        r"\bweapon\b",
        r"\bgun\b",
        r"\bknife\b",
        r"\bfirearm\b",
        r"\bassault\b",
        r"\bfight\b",
        r"\bintruder\b",
        r"\btheft\b",
        r"\bbomb\b"
    ]

    @classmethod
    def evaluate(cls, command: str) -> Tuple[str, Optional[str]]:
        """
        Evaluates command against ethical guardrails and safety policy.
        Returns: (decision, reason)
        decision is one of: 'approved_for_review', 'blocked', 'requires_human_review'
        """
        text = command.lower().strip()

        # 1. Check for prompt injection
        for pat in cls.INJECTION_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return (
                    "blocked",
                    "Security Violation: Prompt injection or arbitrary system command execution attempt detected and blocked."
                )

        # 2. Check for facial recognition & identity tracking
        for pat in cls.FACIAL_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return (
                    "blocked",
                    "Privacy Violation: OmniSense AI strictly prohibits facial recognition and identity tracking. "
                    "Only anonymous spatial aggregate counting (person count & crowd density) is allowed."
                )

        # 3. Check for threat & weapon monitoring (requires human review)
        for pat in cls.THREAT_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return (
                    "requires_human_review",
                    "Safety Notice: Threat detection and weapon-related surveillance requests require mandatory human supervisor clearance."
                )

        return ("approved_for_review", None)
