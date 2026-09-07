"""RideBase V3 — offline multi-label next-service-task research challenger.

V3 answers a different question from every shipped RideBase surface:

    "At the next completed service, which maintenance tasks will be performed?"

It is NOT Maintenance Due, NOT Maintenance Urgency, NOT V2.1 service-return
probability, and NOT a mechanical-failure probability. Nothing in this package
is mounted in production, and no artifact here is read by the live backend.

Source world: RideBase Synthetic Dataset v1.4 (the world the frozen V2.1
production champion was trained and is served on). The v1.4 source tables and
the V2.1 derived outputs are treated as strictly read-only.
"""

V3_VERSION = "v3.0-research"
SOURCE_WORLD = "v1_4"
SEED = 20260907
