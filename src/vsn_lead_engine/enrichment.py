from __future__ import annotations

import gzip
import io
import ipaddress
import json
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from urllib import robotparser
from urllib.parse import urljoin, urlparse, urlunparse

import phonenumbers
import requests

from .models import Lead
from .normalize import normalize_phone


SOCIAL_HOSTS = {
    "instagram": ("instagram.com",),
    "facebook": ("facebook.com",),
    "linkedin": ("linkedin.com",),
    "twitter": ("twitter.com", "x.com"),
    "tiktok": ("tiktok.com",),
}
CONTACT_HINTS = (
    "contact",
    "about",
    "reach",
    "locations",
    "location",
    "connect",
)
EMAIL_RE = re.compile(r"(?i)(?<![\w.+-])([a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,})(?![\w.-])")


class _ContactHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.text_parts: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        low = tag.lower()
        if low in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
            return
        if low == "a":
            for key, value in attrs:
                if key.lower() == "href" and value:
                    self.links.append(str(value).strip())

    def handle_endtag(self, tag: str):
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str):
        if not self._ignored_depth:
            value = " ".join(str(data).split())
            if value:
                self.text_parts.append(value)

    @property
    def visible_text(self) -> str:
        return "\n".join(self.text_parts)


def _country_region(country: str) -> str | None:
    if country == "United States":
        return "US"
    if country == "Canada":
        return "CA"
    return None


def _normalize_site_url(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    try:
        parsed = urlparse(value)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    path = parsed.path or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc, path, "", parsed.query, ""))


def _same_site(left: str, right: str) -> bool:
    try:
        a = (urlparse(left).hostname or "").lower().removeprefix("www.")
        b = (urlparse(right).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return False
    return bool(a and b and a == b)


def _public_host(host: str, port: int) -> bool:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return False
    addresses = {
        item[4][0].split("%", 1)[0]
        for item in infos
        if item and len(item) >= 5 and item[4]
    }
    if not addresses:
        return False
    try:
        return all(ipaddress.ip_address(address).is_global for address in addresses)
    except ValueError:
        return False


def _phones_from_text(text: str, country: str) -> list[str]:
    region = _country_region(country)
    if not text or not region:
        return []
    phones: list[str] = []
    for match in phonenumbers.PhoneNumberMatcher(text, region):
        normalized = normalize_phone(match.raw_string, country)
        if normalized and normalized not in phones:
            phones.append(normalized)
    return phones


def _contact_data(html: str, page_url: str, country: str) -> dict:
    parser = _ContactHTMLParser()
    try:
        parser.feed(html or "")
    except Exception:
        pass

    phone_candidates: list[str] = []
    emails: list[str] = []
    socials = {key: "" for key in SOCIAL_HOSTS}
    contact_links: list[str] = []

    for href in parser.links:
        low = href.lower()
        if low.startswith("tel:"):
            phone = normalize_phone(href[4:].split("?", 1)[0], country)
            if phone and phone not in phone_candidates:
                phone_candidates.append(phone)
            continue
        if low.startswith("mailto:"):
            email = href[7:].split("?", 1)[0].strip().lower()
            if EMAIL_RE.fullmatch(email) and email not in emails:
                emails.append(email)
            continue

        absolute = urljoin(page_url, href)
        try:
            host = (urlparse(absolute).hostname or "").lower()
        except ValueError:
            continue

        for field, domains in SOCIAL_HOSTS.items():
            if not socials[field] and any(host == domain or host.endswith("." + domain) for domain in domains):
                socials[field] = absolute

        if (
            _same_site(page_url, absolute)
            and absolute.startswith(("http://", "https://"))
            and any(hint in low for hint in CONTACT_HINTS)
            and absolute not in contact_links
        ):
            contact_links.append(absolute)

    for phone in _phones_from_text(parser.visible_text, country):
        if phone not in phone_candidates:
            phone_candidates.append(phone)

    for match in EMAIL_RE.finditer(parser.visible_text):
        email = match.group(1).lower()
        if email not in emails:
            emails.append(email)

    return {
        "phones": phone_candidates,
        "emails": emails,
        "socials": socials,
        "contact_links": contact_links,
    }


class ContactEnricher:
    """Bounded public-contact enrichment for official business websites.

    Live sites are checked first. Common Crawl is an optional serial fallback
    used only for the same official domain when live pages do not yield a valid
    phone. The class mutates Lead contact fields in place.
    """

    def __init__(self, config: dict):
        settings = config.get("enrichment", {})
        common = settings.get("common_crawl", {})
        self.enabled = bool(settings.get("enabled", False))
        self.max_candidates = max(0, int(settings.get("max_candidates_per_run", 160)))
        self.max_candidates_per_call = max(
            1,
            min(
                self.max_candidates or 1,
                int(settings.get("max_candidates_per_call", 12)),
            ),
        )
        self.workers = max(1, min(16, int(settings.get("workers", 8))))
        self.timeout = max(1.0, float(settings.get("request_timeout_seconds", 6)))
        self.max_pages = max(1, min(3, int(settings.get("max_pages_per_site", 2))))
        self.max_response_bytes = max(
            65536, min(2_000_000, int(settings.get("max_response_bytes", 524288)))
        )
        self.respect_robots = bool(settings.get("respect_robots_txt", True))
        self.user_agent = str(
            settings.get(
                "user_agent",
                "VSN-Lead-Engine/0.31 (+https://vertexsystemsnetwork.com/)",
            )
        ).strip()
        self.common_enabled = bool(common.get("enabled", False))
        self.common_max_lookups = max(0, int(common.get("max_lookups_per_run", 8)))
        self.common_max_lookups_per_call = max(
            1,
            min(
                self.common_max_lookups or 1,
                int(common.get("max_lookups_per_call", 1)),
            ),
        )
        self.common_min_interval = max(
            1.0, float(common.get("min_interval_seconds", 2.5))
        )
        self.common_index_url = str(
            common.get("index_url", "https://index.commoncrawl.org")
        ).rstrip("/")
        self.common_data_url = str(
            common.get("data_url", "https://data.commoncrawl.org")
        ).rstrip("/")
        self.common_max_record_bytes = max(
            65536, min(2_000_000, int(common.get("max_record_bytes", 1_000_000)))
        )
        self.common_max_decompressed_bytes = max(
            262144,
            min(
                8_000_000,
                int(common.get("max_decompressed_bytes", 4_000_000)),
            ),
        )

        self._budget_lock = threading.Lock()
        self._session_lock = threading.Lock()
        self._robots_lock = threading.Lock()
        self._common_lock = threading.RLock()
        self._sessions: list[requests.Session] = []
        self._local = threading.local()
        self._robots_cache: dict[str, robotparser.RobotFileParser | None] = {}
        self._attempted = 0
        self._common_attempted = 0
        self._last_common_request = 0.0
        self._common_collections: list[str] | None = None

    def close(self):
        with self._session_lock:
            sessions = list(self._sessions)
            self._sessions.clear()
        for session in sessions:
            try:
                session.close()
            except Exception:
                pass

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(
                {
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                }
            )
            self._local.session = session
            with self._session_lock:
                self._sessions.append(session)
        return session

    def _take_candidate_budget(self) -> bool:
        with self._budget_lock:
            if self._attempted >= self.max_candidates:
                return False
            self._attempted += 1
            return True

    def _take_common_budget(self) -> bool:
        with self._budget_lock:
            if self._common_attempted >= self.common_max_lookups:
                return False
            self._common_attempted += 1
            return True

    def _bounded_get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        max_bytes: int | None = None,
        require_status: set[int] | None = None,
    ) -> tuple[requests.Response | None, bytes]:
        current = _normalize_site_url(url)
        if not current:
            return None, b""
        limit = max_bytes or self.max_response_bytes
        response = None

        for _redirect in range(4):
            parsed = urlparse(current)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            if not parsed.hostname or not _public_host(parsed.hostname, port):
                return None, b""

            try:
                response = self._session().get(
                    current,
                    timeout=self.timeout,
                    allow_redirects=False,
                    stream=True,
                    headers=headers,
                )
            except requests.RequestException:
                return None, b""

            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location", "")
                response.close()
                if not location:
                    return None, b""
                current = urljoin(current, location)
                continue
            break

        if response is None:
            return None, b""
        if require_status is not None and response.status_code not in require_status:
            response.close()
            return None, b""
        if require_status is None and response.status_code != 200:
            response.close()
            return None, b""

        content_length = response.headers.get("Content-Length", "")
        if content_length.isdigit() and int(content_length) > limit:
            response.close()
            return None, b""

        chunks = []
        size = 0
        try:
            for chunk in response.iter_content(chunk_size=16384):
                if not chunk:
                    continue
                size += len(chunk)
                if size > limit:
                    response.close()
                    return None, b""
                chunks.append(chunk)
        except requests.RequestException:
            response.close()
            return None, b""

        response.url = current
        body = b"".join(chunks)
        response.close()
        return response, body

    def _robots_allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        with self._robots_lock:
            cached = self._robots_cache.get(origin, ...)
        if cached is not ...:
            return True if cached is None else cached.can_fetch(self.user_agent, url)

        robots_url = origin + "/robots.txt"
        response, body = self._bounded_get(robots_url, max_bytes=131072)
        parser_obj: robotparser.RobotFileParser | None = None
        if response is not None and response.status_code == 200 and body:
            parser_obj = robotparser.RobotFileParser()
            parser_obj.set_url(robots_url)
            parser_obj.parse(body.decode("utf-8", errors="ignore").splitlines())

        with self._robots_lock:
            self._robots_cache[origin] = parser_obj
        return True if parser_obj is None else parser_obj.can_fetch(self.user_agent, url)

    def _fetch_html(self, url: str) -> tuple[str, str]:
        normalized = _normalize_site_url(url)
        if not normalized or not self._robots_allowed(normalized):
            return "", ""
        response, body = self._bounded_get(normalized)
        if response is None or not body:
            return "", ""
        content_type = (response.headers.get("Content-Type", "") or "").lower()
        if "html" not in content_type and "text/" not in content_type:
            return "", ""
        encoding = response.encoding or "utf-8"
        try:
            html = body.decode(encoding, errors="ignore")
        except (LookupError, UnicodeDecodeError):
            html = body.decode("utf-8", errors="ignore")
        return html, response.url

    @staticmethod
    def _merge_data(lead: Lead, data: dict, method: str) -> bool:
        changed = False
        if not normalize_phone(lead.phone, lead.country):
            phones = data.get("phones", []) or []
            if phones:
                lead.phone = phones[0]
                changed = True
        if not lead.email:
            emails = data.get("emails", []) or []
            if emails:
                lead.email = emails[0]
                changed = True
        for field in SOCIAL_HOSTS:
            if not getattr(lead, field, ""):
                value = str((data.get("socials", {}) or {}).get(field, "") or "")
                if value:
                    setattr(lead, field, value)
                    changed = True
        if changed:
            suffix = f"contact enrichment {method}"
            lead.notes = f"{lead.notes}; {suffix}" if lead.notes else suffix
        return changed

    def _live_enrich(self, lead: Lead) -> dict:
        result = {
            "attempted": False,
            "changed": False,
            "phone": False,
            "error": "",
        }
        website = _normalize_site_url(lead.website)
        if not website:
            return result
        result["attempted"] = True
        before_phone = normalize_phone(lead.phone, lead.country)

        try:
            html, final_url = self._fetch_html(website)
            if not html:
                return result
            data = _contact_data(html, final_url or website, lead.country)
            changed = self._merge_data(lead, data, "official_website")
            pages = 1

            if (
                not normalize_phone(lead.phone, lead.country)
                and pages < self.max_pages
            ):
                for link in data.get("contact_links", []) or []:
                    if pages >= self.max_pages:
                        break
                    html2, final2 = self._fetch_html(link)
                    pages += 1
                    if not html2:
                        continue
                    data2 = _contact_data(html2, final2 or link, lead.country)
                    changed = self._merge_data(lead, data2, "official_website") or changed
                    if normalize_phone(lead.phone, lead.country):
                        break

            result["changed"] = changed
            result["phone"] = bool(
                not before_phone and normalize_phone(lead.phone, lead.country)
            )
            return result
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            return result

    def _wait_common_interval(self):
        elapsed = time.monotonic() - self._last_common_request
        delay = self.common_min_interval - elapsed
        if delay > 0:
            time.sleep(delay)
        self._last_common_request = time.monotonic()

    def _common_get_json(self, url: str, params=None):
        self._wait_common_interval()
        try:
            response = self._session().get(
                url,
                params=params,
                timeout=max(self.timeout, 10),
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/json,text/plain;q=0.9,*/*;q=0.1",
                },
            )
            if response.status_code != 200:
                return None
            if len(response.content) > 1_000_000:
                return None
            return response
        except requests.RequestException:
            return None

    def _collections(self) -> list[str]:
        if self._common_collections is not None:
            return self._common_collections
        with self._common_lock:
            if self._common_collections is not None:
                return self._common_collections
            response = self._common_get_json(
                f"{self.common_index_url}/collinfo.json"
            )
            ids: list[str] = []
            if response is not None:
                try:
                    payload = response.json()
                except (ValueError, json.JSONDecodeError):
                    payload = []
                for item in payload if isinstance(payload, list) else []:
                    crawl_id = str((item or {}).get("id", "")).strip()
                    if crawl_id.startswith("CC-MAIN-") and crawl_id not in ids:
                        ids.append(crawl_id)
                    if len(ids) >= 2:
                        break
            self._common_collections = ids
            return ids

    def _common_capture(self, domain: str) -> tuple[dict | None, str]:
        for crawl_id in self._collections():
            response = self._common_get_json(
                f"{self.common_index_url}/{crawl_id}-index",
                params=[
                    ("url", f"{domain}/*"),
                    ("output", "json"),
                    ("filter", "status:200"),
                    ("filter", "mime:text/html"),
                    ("collapse", "urlkey"),
                    ("limit", "5"),
                ],
            )
            if response is None:
                continue
            records = []
            for line in response.text.splitlines():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    records.append(item)
            if not records:
                continue
            records.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
            return records[0], crawl_id
        return None, ""

    def _common_warc_html(self, record: dict) -> str:
        filename = str(record.get("filename", "")).strip()
        try:
            offset = int(record.get("offset", ""))
            length = int(record.get("length", ""))
        except (TypeError, ValueError):
            return ""
        if (
            not filename.startswith("crawl-data/")
            or offset < 0
            or length <= 0
            or length > self.common_max_record_bytes
        ):
            return ""

        end = offset + length - 1
        url = f"{self.common_data_url}/{filename}"
        response, compressed = self._bounded_get(
            url,
            headers={"Range": f"bytes={offset}-{end}"},
            max_bytes=self.common_max_record_bytes,
            require_status={206},
        )
        if response is None or not compressed:
            return ""

        try:
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as handle:
                decompressed = handle.read(self.common_max_decompressed_bytes + 1)
        except (OSError, EOFError):
            return ""
        if len(decompressed) > self.common_max_decompressed_bytes:
            return ""

        text = decompressed.decode("utf-8", errors="ignore")
        html_pos = text.lower().find("<html")
        if html_pos >= 0:
            return text[html_pos:]
        body_split = text.split("\r\n\r\n", 2)
        return body_split[-1] if body_split else text

    def _common_enrich(self, lead: Lead) -> bool:
        website = _normalize_site_url(lead.website)
        if not website:
            return False
        domain = (urlparse(website).hostname or "").lower().removeprefix("www.")
        if not domain:
            return False

        with self._common_lock:
            record, crawl_id = self._common_capture(domain)
            if not record:
                return False
            html = self._common_warc_html(record)
        if not html:
            return False

        capture_url = str(record.get("url") or website)
        data = _contact_data(html, capture_url, lead.country)
        return self._merge_data(
            lead,
            data,
            f"common_crawl:{crawl_id}" if crawl_id else "common_crawl",
        )

    def enrich(self, leads: list[Lead]) -> dict[str, int]:
        stats = {
            "candidates": 0,
            "live_attempted": 0,
            "live_changed": 0,
            "live_phone_recovered": 0,
            "common_crawl_attempted": 0,
            "common_crawl_changed": 0,
            "common_crawl_phone_recovered": 0,
            "skipped_budget": 0,
            "skipped_event_budget": 0,
            "skipped_call_budget": 0,
            "common_crawl_skipped_event_budget": 0,
            "common_crawl_skipped_call_budget": 0,
            "errors": 0,
        }
        if not self.enabled or not leads or self.max_candidates <= 0:
            return stats

        targets: list[Lead] = []
        for lead in leads:
            if normalize_phone(lead.phone, lead.country):
                continue
            if not _normalize_site_url(lead.website):
                continue
            if len(targets) >= self.max_candidates_per_call:
                stats["skipped_call_budget"] += 1
                stats["skipped_budget"] += 1
                continue
            if not self._take_candidate_budget():
                stats["skipped_event_budget"] += 1
                stats["skipped_budget"] += 1
                continue
            targets.append(lead)

        stats["candidates"] = len(targets)
        if not targets:
            return stats

        failed_live: list[Lead] = []
        with ThreadPoolExecutor(max_workers=min(self.workers, len(targets))) as pool:
            futures = {pool.submit(self._live_enrich, lead): lead for lead in targets}
            for future in as_completed(futures):
                lead = futures[future]
                try:
                    result = future.result()
                except Exception:
                    stats["errors"] += 1
                    failed_live.append(lead)
                    continue
                if result.get("attempted"):
                    stats["live_attempted"] += 1
                if result.get("changed"):
                    stats["live_changed"] += 1
                if result.get("phone"):
                    stats["live_phone_recovered"] += 1
                if result.get("error"):
                    stats["errors"] += 1
                if not normalize_phone(lead.phone, lead.country):
                    failed_live.append(lead)

        if not self.common_enabled or self.common_max_lookups <= 0:
            return stats

        common_used_this_call=0
        for index,lead in enumerate(failed_live):
            remaining=len(failed_live)-index
            if common_used_this_call >= self.common_max_lookups_per_call:
                stats["common_crawl_skipped_call_budget"] += remaining
                break
            if not self._take_common_budget():
                stats["common_crawl_skipped_event_budget"] += remaining
                break
            common_used_this_call += 1
            stats["common_crawl_attempted"] += 1
            before = normalize_phone(lead.phone, lead.country)
            try:
                changed = self._common_enrich(lead)
            except Exception:
                stats["errors"] += 1
                continue
            if changed:
                stats["common_crawl_changed"] += 1
            if not before and normalize_phone(lead.phone, lead.country):
                stats["common_crawl_phone_recovered"] += 1

        return stats


def build_contact_enricher(config: dict) -> ContactEnricher | None:
    settings = config.get("enrichment", {})
    if not bool(settings.get("enabled", False)):
        return None
    return ContactEnricher(config)
