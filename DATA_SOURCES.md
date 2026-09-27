# Data Sources and Compliance

## Overture Maps Places — production default

The production free-discovery source is Overture Maps Places. The Places theme is
published from multiple providers under permissive licenses documented by the
Overture Maps Foundation (including CDLA Permissive 2.0, Apache 2.0 and CC0,
depending on the contributing source).

The engine:

- reads the public Overture GeoParquet release from AWS using DuckDB predicate pushdown;
- resolves the latest release through the Overture STAC catalog;
- stores the Overture feature ID in the source fingerprint;
- records Overture/source-provider context in lead notes;
- only accepts publicly listed business contact fields present in the dataset.

Reference:
- https://docs.overturemaps.org/guides/places/
- https://docs.overturemaps.org/attribution/

## OpenStreetMap / Overpass — optional only

The recurring commercial workflow does not use public community Overpass
instances by default. The Overpass adapter requires an explicit
`OVERPASS_ENDPOINT` and rejects known public community hosts. It is intended
for a self-hosted or otherwise approved endpoint.

This keeps the scheduled engine from overusing a public service intended for
small/fair-use workloads.


## Official website contact enrichment — production P1

When Overture has a business website but no usable phone, the engine may inspect
the publicly accessible official website before rejecting the candidate.

Controls:

- only the Overture-listed official website is used as the starting domain;
- private, loopback, link-local and other non-public network targets are rejected;
- redirects are revalidated before following;
- `robots.txt` is respected when available;
- at most a small configured number of same-site pages are inspected;
- response bytes, timeouts, concurrency and total candidates are hard-capped;
- recovered phone numbers must still pass the same US/Canada phone validation;
- enrichment does not bypass taxonomy classification or permanent R2 dedupe.

The engine records the enrichment method in the lead notes when public contact
fields are recovered.

## Common Crawl — bounded archival fallback

Common Crawl is used only as a fallback for the same official business domain
when the live site does not yield a valid phone. It is not used as a broad
business-discovery or search engine.

The CDXJ collection is resolved dynamically from Common Crawl's collection
metadata. Index calls are serial and rate-limited, with a small per-run lookup
budget. Only bounded HTML WARC records are fetched with HTTP Range requests, and
the isolated archive result still has to pass normal phone validation and R2
dedupe before acceptance.

References:

- https://commoncrawl.org/cdxj-index
- https://commoncrawl.org/get-started
- https://commoncrawl.org/faq
