from __future__ import annotations
import os,time,requests
from ..models import Lead

CATEGORY_FILTERS={
"AI & Automation":['["office"="it"]'],
"Medical & Clinics":['["amenity"~"clinic|doctors|dentist"]','["healthcare"]'],
"Property & Real Estate":['["office"="estate_agent"]'],
"Business & Consulting":['["office"~"consulting|company"]'],
"IT & Software":['["office"="it"]','["craft"="electronics_repair"]'],
"Media & Creative":['["office"~"advertising|graphic_design"]'],
"Other Website-Critical":['["craft"]','["office"="architect"]'],
"Spa":['["leisure"="spa"]','["shop"="beauty"]'],
"Salon":['["shop"~"hairdresser|beauty|nail"]'],
"Cars":['["shop"~"car|car_repair|tyres"]'],
"Motorbikes":['["shop"~"motorcycle|motorcycle_repair"]'],
"Insurance":['["office"="insurance"]'],
}

class OverpassSource:
    name="OpenStreetMap/Overpass"
    def __init__(self,timeout_seconds=45,min_interval_seconds=8):
        self.endpoint=os.getenv("OVERPASS_ENDPOINT","https://overpass-api.de/api/interpreter")
        self.timeout_seconds=timeout_seconds
        self.min_interval_seconds=min_interval_seconds
        self._last_request=0.0
    def _rate_limit(self):
        elapsed=time.monotonic()-self._last_request
        if elapsed<self.min_interval_seconds:
            time.sleep(self.min_interval_seconds-elapsed)
    def search(self,category,location):
        filters=CATEGORY_FILTERS.get(category,[])
        if not filters: return []
        city=location["city"].replace('"','\"')
        country=location["country"]; region=location["region"]
        pieces=[]
        for f in filters:
            pieces.append(f'nwr{f}["name"]["phone"](area.searchArea);')
            pieces.append(f'nwr{f}["name"]["contact:phone"](area.searchArea);')
        query=f'''[out:json][timeout:{self.timeout_seconds}];
area["name"="{city}"]["boundary"="administrative"]->.searchArea;
(
{chr(10).join(pieces)}
);
out center tags;'''
        self._rate_limit()
        response=requests.post(self.endpoint,data={"data":query},timeout=self.timeout_seconds+10,headers={"User-Agent":"VSN-Lead-Engine/0.1 (+https://github.com/Vertex-Systems-Network/vsn-lead-engine)"})
        self._last_request=time.monotonic()
        response.raise_for_status()
        leads=[]
        for item in response.json().get("elements",[]):
            tags=item.get("tags",{})
            phone=tags.get("phone") or tags.get("contact:phone") or ""
            name=tags.get("name") or ""
            if not phone or not name: continue
            center=item.get("center",{})
            lat=item.get("lat",center.get("lat")); lon=item.get("lon",center.get("lon"))
            osm_type=item.get("type",""); osm_id=item.get("id","")
            source_id=f"osm:{osm_type}/{osm_id}"
            leads.append(Lead(country=country,category=category,business_name=name,phone=phone,city=tags.get("addr:city") or city,region=tags.get("addr:state") or region,postal_code=tags.get("addr:postcode",""),street_address=" ".join(p for p in [tags.get("addr:housenumber",""),tags.get("addr:street","")] if p),latitude=lat,longitude=lon,website=tags.get("website") or tags.get("contact:website") or "",email=tags.get("email") or tags.get("contact:email") or "",source=self.name,source_id=source_id,source_url=f"https://www.openstreetmap.org/{osm_type}/{osm_id}" if osm_type and osm_id else "",notes=f"Free public source; OSM source id {source_id}"))
        return leads
