"""Offline search-setup helper: bounded suggestions with NO model or provider calls.

This deterministic baseline is NOT presented as AI inference. Its output is a
user-review-only proposal; the existing saved-draft form remains authoritative.
Never send user instructions to a model, source provider, or queue from here.
"""

import re

from django import forms
from rest_framework.exceptions import ValidationError

from .serializers import SearchSerializer

MAX_INTENT_LENGTH = 280

# All patterns and output labels are trusted code, never user-configurable prompts.
COUNTRY_PATTERNS = (
    ("US", re.compile(r"\b(?:united states(?: of america)?|usa|u\\.s\\.|us)\b", re.I)),
    ("CA", re.compile(r"\bcanada\b", re.I)),
)
CATEGORY_PATTERNS = (
    ("spa", re.compile(r"\bspas?\b", re.I)),
    ("salon", re.compile(r"\bsalons?\b", re.I)),
    ("car dealer", re.compile(r"\b(?:car dealers?|car dealerships?)\b", re.I)),
    ("motorcycle dealer", re.compile(r"\b(?:motorcycle|motorbike)\s+(?:dealers?|shops?)\b", re.I)),
    ("insurance agency", re.compile(r"\b(?:insurance agencies|insurance agency|insurance agents?)\b", re.I)),
    ("dentist", re.compile(r"\b(?:dentists?|dental clinics?)\b", re.I)),
    ("restaurant", re.compile(r"\brestaurants?\b", re.I)),
    ("cleaning service", re.compile(r"\bcleaning services?\b", re.I)),
    ("real estate agent", re.compile(r"\breal estate agents?\b", re.I)),
    ("accountant", re.compile(r"\baccountants?\b", re.I)),
    ("law firm", re.compile(r"\blaw firms?\b", re.I)),
    ("plumber", re.compile(r"\bplumbers?\b", re.I)),
)


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
        value = self.cleaned_data["intent"].strip()
        # The preview stores nothing. Still refuse obvious contact and credential
        # material before classification, and never reflect raw intent in the page.
        if (
            any(ord(char) < 32 and char not in "\t\n\r" for char in value)
            or re.search(r"\b(?:https?://|www\\.)", value, re.I)
            or re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}", value)
            or re.search(r"(?<!\\w)\\+?\\d[\\d().\s-]{6,}\\d(?!\\w)", value)
        ):
            raise forms.ValidationError(
                "Remove links, email addresses, telephone numbers and control characters."
            )
        return value


def search_assistance_preview(intent):
    """Fixed-pattern allowlist extraction; no probabilistic completion or auto-action."""
    if not isinstance(intent, str) or not (4 <= len(intent) <= MAX_INTENT_LENGTH):
        raise ValueError("Invalid preview intent length.")
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
