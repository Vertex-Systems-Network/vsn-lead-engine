"""Offline search-setup helper: bounded suggestions with NO model or provider calls.

This deterministic baseline is NOT presented as AI inference. Its output is a
user-review-only proposal; the existing saved-draft form remains authoritative.
Never send user instructions to a model, source provider, or queue from here.
"""

import re
import unicodedata

from django import forms
from rest_framework.exceptions import ValidationError

from .serializers import SearchSerializer

MAX_INTENT_LENGTH = 280

# All patterns and output labels are trusted code, never user-configurable prompts.
COUNTRY_PATTERNS = (
    (
        "US",
        re.compile(
            r"\b(?:united states(?: of america)?|usa)\b"
            r"|(?<![A-Za-z])(?-i:US|U\.S\.)(?![A-Za-z])",
            re.I,
        ),
    ),
    ("CA", re.compile(r"\bcanada\b", re.I)),
)
CATEGORY_PATTERNS = (
    ("spa", re.compile(r"\bspas?\b", re.I)),
    ("salon", re.compile(r"\bsalons?\b", re.I)),
    ("car dealer", re.compile(r"\b(?:car dealers?|car dealerships?)\b", re.I)),
    ("motorcycle dealer", re.compile(r"\b(?:motorcycle|motorbike)\s+(?:dealers?|shops?)\b", re.I)),
    (
        "insurance agency",
        re.compile(r"\b(?:insurance agencies|insurance agency|insurance agents?)\b", re.I),
    ),
    ("dentist", re.compile(r"\b(?:dentists?|dental clinics?)\b", re.I)),
    ("restaurant", re.compile(r"\brestaurants?\b", re.I)),
    ("cleaning service", re.compile(r"\bcleaning services?\b", re.I)),
    ("real estate agent", re.compile(r"\breal estate agents?\b", re.I)),
    ("accountant", re.compile(r"\baccountants?\b", re.I)),
    ("law firm", re.compile(r"\blaw firms?\b", re.I)),
    ("plumber", re.compile(r"\bplumbers?\b", re.I)),
)


# The preview cannot safely represent a negative/excluded category/country.
# It must abstain rather than silently include an unwanted target. Likewise
# do not drop unsupported countries from a mixed-market request.
EXCLUSION_PATTERN = re.compile(
    r"\b(?:no|not|without|exclude|excluding|except|avoid|skip|omit|ignore|"
    r"neither|never|don't|doesn't|do not)\b",
    re.I,
)
UNSUPPORTED_GEO_PATTERN = re.compile(
    r"\b(?:united kingdom|uk|england|scotland|pakistan|uae|united arab emirates|"
    r"india|australia|germany|france|mexico|brazil|spain|europe|eu)\b",
    re.I,
)


# Defense in depth: all callers (including future AI adapters) must use the same
# strict data-minimization boundary. These patterns cover common secret formats,
# not every possible credential or sensitive item; do not accept private data.
WEB_LINK_PATTERN = re.compile(r"\b(?:https?://|www\.)", re.I)
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"(?<!\w)\+?\d[\d().\s-]{6,}\d(?!\w)")
KEY_PREFIX_PATTERN = re.compile(
    r"\b(?:sk-(?:proj-|test-|live-)?[A-Za-z0-9_-]{12,}"
    r"|sk_(?:live|test)_[A-Za-z0-9]{12,}"
    r"|gh[pousr]_[A-Za-z0-9_]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16})\b"
)
ASSIGNMENT_PATTERN = re.compile(
    r"\b(?:api[_\s-]?key|access[_\s-]?token|refresh[_\s-]?token|"
    r"client[_\s-]?secret|secret[_\s-]?key|password|passwd|"
    r"authorization)\s*[:=]\s*['\"]?\S+",
    re.I,
)
BEARER_PATTERN = re.compile(r"\bbearer\s+[A-Za-z0-9._~+/-]{8,}\b", re.I)
UNSAFE_INPUT_PATTERNS = (
    WEB_LINK_PATTERN,
    EMAIL_PATTERN,
    PHONE_PATTERN,
    KEY_PREFIX_PATTERN,
    ASSIGNMENT_PATTERN,
    BEARER_PATTERN,
)


def validated_search_intent(value):
    """Validate confidential input before *any* classification or model call.

    Returns sanitized input on success; raw or partial user input is never
    included in a validation error. Does not persist, log or send anything.
    """
    if not isinstance(value, str):
        raise ValueError("Invalid search-assistance input.")
    intent = value.strip()
    if (
        not (4 <= len(intent) <= MAX_INTENT_LENGTH)
        or any(
            unicodedata.category(char) in {"Cf", "Cs"}
            or (unicodedata.category(char) == "Cc" and char not in "\t\n\r")
            for char in intent
        )
        or any(pattern.search(intent) for pattern in UNSAFE_INPUT_PATTERNS)
    ):
        raise ValueError(
            "Remove links, contact details, keys, secrets, and unsupported characters."
        )
    return intent


class SearchAssistForm(forms.Form):
    intent = forms.CharField(
        min_length=4,
        max_length=MAX_INTENT_LENGTH,
        widget=forms.Textarea(attrs={"rows": 3, "autocomplete": "off"}),
        help_text=(
            "Describe business categories and countries (US/Canada only). "
            "Do not include private contacts, API keys or company secrets."
        ),
    )

    def clean_intent(self):
        try:
            return validated_search_intent(self.cleaned_data["intent"])
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from None


def search_assistance_preview(intent):
    """Fixed-pattern allowlist extraction; no probabilistic completion or auto-action."""
    intent = validated_search_intent(intent)
    # Conservative abstention is an explicit safety feature, not AI inference.
    if EXCLUSION_PATTERN.search(intent):
        return {
            "mode": "rules_only_no_model",
            "status": "needs_details",
            "model_invoked": False,
            "needs_user_review": True,
            "search": None,
            "missing": [
                "Exclusions or negations require manual review. State only positive targets."
            ],
        }
    if UNSUPPORTED_GEO_PATTERN.search(intent):
        return {
            "mode": "rules_only_no_model",
            "status": "needs_details",
            "model_invoked": False,
            "needs_user_review": True,
            "search": None,
            "missing": ["Only US and Canada are supported. Remove unsupported countries."],
        }
    countries = [code for code, pattern in COUNTRY_PATTERNS if pattern.search(intent)]
    categories = [label for label, pattern in CATEGORY_PATTERNS if pattern.search(intent)]
    missing = []
    if not countries:
        missing.append("Specify United States/US or Canada explicitly.")
    if not categories:
        missing.append("Specify at least one supported business category.")
    if missing:
        return {
            "mode": "rules_only_no_model",
            "status": "needs_details",
            "model_invoked": False,
            "needs_user_review": True,
            "search": None,
            "missing": missing,
        }
    serializer = SearchSerializer(
        data={
            "countries": countries,
            "categories": categories,
            "statuses": [],
            "required_fields": ["phone"],
            "source_codes": [],
            "result_limit": 25,
        }
    )
    if not serializer.is_valid():
        raise ValidationError("Suggested scope could not be validated.")
    return {
        "mode": "rules_only_no_model",
        "status": "ready_for_manual_review",
        "model_invoked": False,
        "needs_user_review": True,
        "search": serializer.validated_data,
        "missing": [],
    }
