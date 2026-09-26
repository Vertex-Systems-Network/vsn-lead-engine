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
