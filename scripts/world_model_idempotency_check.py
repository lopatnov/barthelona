#!/usr/bin/env python3
"""Idempotency check for World Model (AGENTS.md invariant).

Re-running the ingest pipeline on the same input produces the same world state.
The diff must be empty. Exit 0 on empty diff; pass --mutate to prove the check
can fail (exit 1).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

# Add src to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from barthelona.world_model import (
    WorldModel,
    WorldModelOptions,
    IngestObservation,
    IngestEntity,
    Provenance,
    ProvenanceKind,
    canonical_json,
)


FIXTURE = [
    {
        "external_id": "art-101",
        "title": "Fed holds rates steady amid mixed signals",
        "at": "2026-05-17T14:00:00.000Z",
        "source": {
            "kind": ProvenanceKind.RSS,
            "at": datetime(2026, 5, 17, 14, 0, 0),
            "url": "https://example.com/a",
        },
        "entities": [
            {"type": "person", "name": "Jerome Powell"},
            {"type": "org", "name": "Federal Reserve"},
        ],
    },
    {
        "external_id": "art-102",
        "title": "Powell signals patience on cuts",
        "at": "2026-05-17T16:30:00.000Z",
        "source": {
            "kind": ProvenanceKind.RSS,
            "at": datetime(2026, 5, 17, 16, 30, 0),
            "url": "https://example.com/b",
        },
        "entities": [
            {"type": "person", "name": "Jerome Powell"},
            {"type": "org", "name": "Federal Reserve"},
        ],
    },
    {
        "external_id": "art-103",
        "title": "Markets unmoved by the announcement",
        "at": "2026-05-17T18:00:00.000Z",
        "source": {
            "kind": ProvenanceKind.API,
            "at": datetime(2026, 5, 17, 18, 0, 0),
        },
        "entities": [{"type": "org", "name": "Federal Reserve"}],
    },
]


def create_observations(mutate: bool = False) -> list[IngestObservation]:
    """Create observations from fixture, optionally mutating the first one."""
    observations = []
    for i, item in enumerate(FIXTURE):
        if mutate and i == 0:
            title = item["title"] + " (edited)"
        else:
            title = item["title"]
        
        obs = IngestObservation(
            external_id=item["external_id"],
            title=title,
            at=item["at"],
            source=Provenance(**item["source"]),
            entities=[IngestEntity(**e) for e in item["entities"]],
        )
        observations.append(obs)
    return observations


async def main() -> int:
    parser = argparse.ArgumentParser(description="World Model idempotency check")
    parser.add_argument("--mutate", action="store_true", 
                       help="Mutate the second run to prove check can fail")
    args = parser.parse_args()
    
    mutate = args.mutate
    
    clock = lambda: datetime(2026, 5, 18, 0, 0, 0)
    
    world = WorldModel(WorldModelOptions(
        storage="memory",
        namespace="idem",
        clock=clock,
    ))
    
    # Run 1
    obs1 = create_observations(mutate=False)
    r1 = await world.ingest(obs1)
    shape1 = world.state_shape_canonical()
    print(f"run 1: processed={r1.processed} clusters={r1.clusters} changed={r1.changed}")
    
    # Run 2 (same or mutated)
    obs2 = create_observations(mutate=mutate)
    r2 = await world.ingest(obs2)
    shape2 = world.state_shape_canonical()
    print(f"run 2: processed={r2.processed} skipped={r2.skipped_unchanged} changed={r2.changed}")
    
    if shape1 == shape2:
        print("diff: empty")
        if mutate:
            print("ERROR: expected the mutation to change state; it did not", file=sys.stderr)
            return 1
        return 0
    else:
        print("diff: NON-EMPTY")
        if mutate:
            return 0  # Expected to fail with mutation
        return 1


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))