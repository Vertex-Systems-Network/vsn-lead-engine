from __future__ import annotations
from .models import Lead

def score_lead(lead: Lead) -> int:
    website_need=5 if lead.website else 15
    contactability=10+(10 if lead.email else 0)
    field_fit=20
    maps_evidence=10 if lead.rating is not None and lead.reviews is not None else 5 if (lead.rating is not None or lead.reviews is not None) else 0
    contact_person=10 if lead.contact_person else 0
    return min(100,website_need+contactability+field_fit+maps_evidence+contact_person)

def score_band(score: int) -> str:
    if score>=75: return "High"
    if score>=50: return "Medium"
    return "Low"

def pitch(lead: Lead) -> str:
    return f"Hi {lead.business_name}, VSN can strengthen your online credibility and discoverability with a branded website/profile plus ongoing social-media management to help turn local visibility into consistent enquiries and leads."
