#!/usr/bin/env python3
"""World Model conformance runner.

Executes the World Model implementation against the spec's load-bearing
invariants and prints a scorecard.

Required exports from barthelona.world_model:
- WorldModel (class)
- entity_id_from_name
- normalize_name
- decide (merge banding)
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from barthelona.world_model import (
    WorldModel,
    WorldModelOptions,
    Provenance,
    ProvenanceKind,
    entity_id_from_name,
    normalize_name,
    decide,
)


class CaseResult:
    def __init__(self, id: str, description: str, status: str, detail: str = ""):
        self.id = id
        self.description = description
        self.status = status
        self.detail = detail


results: list[CaseResult] = []


async def record(id: str, description: str, fn):
    """Record a test case result."""
    try:
        await fn()
        results.append(CaseResult(id, description, "PASS"))
    except Exception as err:
        results.append(CaseResult(id, description, "FAIL", str(err)))


def assert_true(cond: bool, msg: str):
    """Assert that condition is true."""
    if not cond:
        raise AssertionError(msg)


async def run_conformance() -> int:
    """Run all conformance tests."""
    
    # Test data
    OBSERVATIONS = [
        {
            "externalId": "a1",
            "title": "Fed holds rates",
            "at": "2026-05-17T14:00:00.000Z",
            "source": {"kind": ProvenanceKind.RSS, "at": "2026-05-17T14:00:00.000Z"},
            "entities": [{"type": "person", "name": "Jerome Powell"}],
        },
        {
            "externalId": "a2",
            "title": "Powell signals patience",
            "at": "2026-05-17T16:30:00.000Z",
            "source": {"kind": ProvenanceKind.RSS, "at": "2026-05-17T16:30:00.000Z"},
            "entities": [{"type": "person", "name": "Jerome Powell"}],
        },
    ]
    
    clock = lambda: datetime(2026, 5, 18, 0, 0, 0)
    
    # sid-001: stable ids - diacritics and NBSP normalize identically
    def test_sid_001():
        assert_true(
            normalize_name("José\u00a0\u00a0García") == normalize_name("Jose Garcia"),
            "accented + NBSP name must normalize to the plain form"
        )
        assert_true(
            entity_id_from_name("person", "José García") == entity_id_from_name("person", "jose garcia"),
            "same normalized name must produce the same id"
        )
    
    record("sid-001", "stable ids: diacritics and NBSP normalize identically (NFKD + strip marks)", test_sid_001)
    
    # sid-002: stable ids - distinct names stay distinct
    def test_sid_002():
        assert_true(
            entity_id_from_name("org", "Acme Corp") != entity_id_from_name("org", "Acme Corporation"),
            "different names must produce different ids"
        )
        assert_true(
            entity_id_from_name("person", "x") != entity_id_from_name("org", "x"),
            "type participates in the key"
        )
    
    record("sid-002", "stable ids: distinct names stay distinct (no over-normalization)", test_sid_002)
    
    # band-001: merge bands at boundaries
    def test_band_001():
        assert_true(decide(0.85) == "auto-merge", "0.85 exactly is auto-merge (>= reading)")
        assert_true(decide(0.84) == "review", "0.84 queues for review")
        assert_true(decide(0.82) == "review", "0.82 exactly queues")
        assert_true(decide(0.81) == "new", "0.81 is a new entity")
    
    record("band-001", "merge bands at the boundaries: 0.85 auto, 0.84 review, 0.82 review, 0.81 new", test_band_001)
    
    # prov-001: writes without provenance are rejected
    async def test_prov_001():
        world = WorldModel(WorldModelOptions(storage="memory", namespace="conf"))
        rejected = False
        try:
            await world.upsert_entity(type="person", name="No Provenance", source=None)
        except Exception:
            rejected = True
        assert_true(rejected, "no provenance, no write")
    
    await record("prov-001", "writes without provenance are rejected", test_prov_001)
    
    # idem-001: ingest idempotency
    async def test_idem_001():
        world = WorldModel(WorldModelOptions(storage="memory", namespace="conf", clock=clock))
        
        # Convert observations to proper format
        from barthelona.world_model import IngestObservation, IngestEntity
        obs_list = [
            IngestObservation(
                external_id=o["externalId"],
                title=o["title"],
                at=o["at"],
                source=Provenance(**o["source"]),
                entities=[IngestEntity(**e) for e in o["entities"]],
            )
            for o in OBSERVATIONS
        ]
        
        await world.ingest(obs_list)
        shape1 = world.state_shape_canonical()
        second = await world.ingest(obs_list)
        
        assert_true(second.changed is False, "second run must report changed=false")
        assert_true(world.state_shape_canonical() == shape1, "canonical state must be identical after re-ingest")
    
    await record("idem-001", "ingest idempotency: same batch twice produces an empty diff", test_idem_001)
    
    # idem-002: idempotency check can fail with mutation
    async def test_idem_002():
        world = WorldModel(WorldModelOptions(storage="memory", namespace="conf", clock=clock))
        
        from barthelona.world_model import IngestObservation, IngestEntity
        obs_list = [
            IngestObservation(
                external_id=o["externalId"],
                title=o["title"],
                at=o["at"],
                source=Provenance(**o["source"]),
                entities=[IngestEntity(**e) for e in o["entities"]],
            )
            for o in OBSERVATIONS
        ]
        
        await world.ingest(obs_list)
        shape1 = world.state_shape_canonical()
        
        # Mutate first observation
        mutated = [
            IngestObservation(
                external_id=OBSERVATIONS[0]["externalId"],
                title=OBSERVATIONS[0]["title"] + " (edited)",
                at=OBSERVATIONS[0]["at"],
                source=Provenance(**OBSERVATIONS[0]["source"]),
                entities=[IngestEntity(**e) for e in OBSERVATIONS[0]["entities"]],
            ),
            IngestObservation(
                external_id=OBSERVATIONS[1]["externalId"],
                title=OBSERVATIONS[1]["title"],
                at=OBSERVATIONS[1]["at"],
                source=Provenance(**OBSERVATIONS[1]["source"]),
                entities=[IngestEntity(**e) for e in OBSERVATIONS[1]["entities"]],
            ),
        ]
        
        run = await world.ingest(mutated)
        assert_true(run.changed is True, "an edited observation must report changed=true")
        assert_true(world.state_shape_canonical() != shape1, "canonical state must differ after a real edit")
    
    await record("idem-002", "the idempotency check can fail: a mutated batch changes the shape", test_idem_002)
    
    # bitemp-001: bitemporal edges
    async def test_bitemp_001():
        world = WorldModel(WorldModelOptions(storage="memory", namespace="conf"))
        at = lambda s: Provenance(kind=ProvenanceKind.MANUAL, at=datetime.fromisoformat(s.replace("Z", "+00:00")))
        
        player = await world.upsert_entity(
            type="player",
            external_key={"system": "g", "id": "p1"},
            attrs={},
            source=at("2087-01-01T00:00:00.000Z")
        )
        team_a = await world.upsert_entity(
            type="team",
            external_key={"system": "g", "id": "a"},
            attrs={},
            source=at("2087-01-01T00:00:00.000Z")
        )
        team_b = await world.upsert_entity(
            type="team",
            external_key={"system": "g", "id": "b"},
            attrs={},
            source=at("2088-03-01T00:00:00.000Z")
        )
        
        await world.relate(
            from_=player.id,
            type="plays-for",
            to=team_a.id,
            valid_from="2087-01-01T00:00:00.000Z",
            source=at("2087-01-01T00:00:00.000Z")
        )
        await world.relate(
            from_=player.id,
            type="plays-for",
            to=team_b.id,
            valid_from="2088-03-01T00:00:00.000Z",
            source=at("2088-03-01T00:00:00.000Z")
        )
        
        graph = world.view("graph")
        now = graph.neighbors_of(player.id, via="plays-for")
        assert_true(
            len(now) == 1 and now[0].id == team_b.id,
            f"open edge should point at team b; got {[e.id for e in now]}"
        )
        
        then = graph.neighbors_of(player.id, via="plays-for", at="2087-06-01T00:00:00.000Z")
        assert_true(
            len(then) == 1 and then[0].id == team_a.id,
            f"2087 query should return team a; got {[e.id for e in then]}"
        )
    
    await record("bitemp-001", "bitemporal edges: a superseding edge closes the old one; point-in-time queries respect validity", test_bitemp_001)
    
    # audit-001: every mutation writes an audit entry in order
    async def test_audit_001():
        world = WorldModel(WorldModelOptions(storage="memory", namespace="conf"))
        await world.upsert_entity(
            type="x",
            name="Audit One",
            source=Provenance(kind=ProvenanceKind.MANUAL, at=datetime(2026, 1, 1))
        )
        await world.upsert_entity(
            type="x",
            name="Audit Two",
            source=Provenance(kind=ProvenanceKind.MANUAL, at=datetime(2026, 1, 2))
        )
        
        audit = world.audit()
        assert_true(len(audit) >= 2, f"expected >= 2 audit entries, got {len(audit)}")
        for i in range(1, len(audit)):
            assert_true(audit[i].seq > audit[i - 1].seq, "audit seq must be strictly increasing")
    
    await record("audit-001", "every mutation writes an audit entry in order", test_audit_001)
    
    # Print results
    pass_count = sum(1 for r in results if r.status == "PASS")
    total = len(results)
    
    print(f"\nWorld Model conformance: implementation = barthelona.world_model\n")
    for r in results:
        print(f"  {r.status} {r.id} {r.description}{f'\\n       {r.detail}' if r.detail else ''}")
    
    print(f"\n  {pass_count}/{total} checks passed")
    return 0 if pass_count == total else 1


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(run_conformance()))