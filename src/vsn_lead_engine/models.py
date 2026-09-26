from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

@dataclass(slots=True)
class Lead:
    country: str
    category: str
    business_name: str
    phone: str
    city: str
    region: str
    source: str
    source_id: str
    street_address: str = ""
    postal_code: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    website: str = ""
    email: str = ""
    rating: Optional[float] = None
    reviews: Optional[int] = None
    contact_person: str = ""
    source_url: str = ""
    notes: str = ""
    date_added: str = field(default_factory=lambda: date.today().isoformat())

    @property
    def website_status(self) -> str:
        return "Active" if self.website else "Unknown"
