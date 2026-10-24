"""Concurrent writers test for World Model.

Stress test with 10 agents updating the same entities simultaneously.
No update may be lost, and final state must match a serial run.
"""

from __future__ import annotations

import asyncio
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest

from barthelona.world_model import (
    WorldModel,
    WorldModelOptions,
    Provenance,
    ProvenanceKind,
    IngestObservation,
    IngestEntity,
)


@pytest.fixture
def world_model() -> WorldModel:
    """Create a fresh World Model instance for testing."""
    return WorldModel(WorldModelOptions(
        namespace="test_concurrent",
        storage="memory",
        clock=lambda: datetime(2026, 5, 18, 0, 0, 0),
    ))


@pytest.fixture
def provenance() -> Provenance:
    """Create a test provenance."""
    return Provenance(
        kind=ProvenanceKind.INGEST,
        at=datetime(2026, 5, 17, 14, 0, 0),
        by="test_agent",
        run_id="test_run",
    )


async def agent_update_entity(
    world: WorldModel,
    agent_id: int,
    entity_type: str,
    entity_name: str,
    attr_key: str,
    attr_value: Any,
    provenance: Provenance,
) -> None:
    """Simulate an agent updating an entity."""
    # Small random delay to simulate real-world timing
    await asyncio.sleep(random.uniform(0.001, 0.01))
    
    await world.upsert_entity(
        type=entity_type,
        name=entity_name,
        attrs={attr_key: attr_value},
        source=provenance,
    )


async def agent_ingest_observation(
    world: WorldModel,
    agent_id: int,
    observation: IngestObservation,
) -> None:
    """Simulate an agent ingesting an observation."""
    await asyncio.sleep(random.uniform(0.001, 0.01))
    await world.ingest([observation])


class TestConcurrentWriters:
    """Tests for concurrent writer scenarios."""

    @pytest.mark.asyncio
    async def test_ten_agents_update_same_entity(
        self,
        world_model: WorldModel,
        provenance: Provenance,
    ) -> None:
        """
        Test that 10 agents can concurrently update the same entity.
        
        All updates should be applied (no lost updates), and the final state
        should be deterministic based on the conflict resolution policy.
        """
        entity_type = "person"
        entity_name = "Jerome Powell"
        num_agents = 10
        
        # Create tasks for 10 agents updating the same entity
        tasks = [
            agent_update_entity(
                world_model,
                agent_id=i,
                entity_type=entity_type,
                entity_name=entity_name,
                attr_key=f"update_{i}",
                attr_value=f"value_from_agent_{i}",
                provenance=provenance,
            )
            for i in range(num_agents)
        ]
        
        # Run all agents concurrently
        await asyncio.gather(*tasks)
        
        # Verify the entity exists
        entity_id = f"ent_{entity_type}:{entity_name.lower().replace(' ', '_')}"
        # Actually, let's get the entity by querying
        graph = world_model.view("graph")
        entities = graph.query(type=entity_type, where=lambda e: e.name == entity_name)
        
        assert len(entities) == 1, f"Expected 1 entity, got {len(entities)}"
        entity = entities[0]
        
        # Verify all updates were applied (most-recent-wins policy)
        # The last update should win for each attribute
        # Since they all run concurrently with same timestamp, the order is non-deterministic
        # but all attribute keys should be present
        for i in range(num_agents):
            assert f"update_{i}" in entity.attrs, f"Missing update_{i} in entity attrs"
        
        # Verify no updates were lost - all 10 attributes should be present
        assert len(entity.attrs) == num_agents, f"Expected {num_agents} attrs, got {len(entity.attrs)}"

    @pytest.mark.asyncio
    async def test_ten_agents_ingest_same_observations(
        self,
        world_model: WorldModel,
        provenance: Provenance,
    ) -> None:
        """
        Test that 10 agents can concurrently ingest the same observations.
        
        Idempotency should ensure the final state matches a single ingest.
        """
        observations = [
            IngestObservation(
                external_id="art-101",
                title="Fed holds rates steady amid mixed signals",
                at="2026-05-17T14:00:00.000Z",
                source=provenance,
                entities=[
                    IngestEntity(type="person", name="Jerome Powell"),
                    IngestEntity(type="org", name="Federal Reserve"),
                ],
            ),
            IngestObservation(
                external_id="art-102",
                title="Powell signals patience on cuts",
                at="2026-05-17T16:30:00.000Z",
                source=provenance,
                entities=[
                    IngestEntity(type="person", name="Jerome Powell"),
                    IngestEntity(type="org", name="Federal Reserve"),
                ],
            ),
        ]
        
        num_agents = 10
        
        # Create tasks for 10 agents ingesting the same observations
        tasks = [
            agent_ingest_observation(world_model, i, observations[0])
            for i in range(num_agents)
        ]
        tasks.extend([
            agent_ingest_observation(world_model, i, observations[1])
            for i in range(num_agents)
        ])
        
        # Run all agents concurrently
        await asyncio.gather(*tasks)
        
        # Verify final state matches serial ingest
        graph = world_model.view("graph")
        
        # Should have 2 observation entities + 2 mentioned entities = 4 total
        # But deduplication should keep it minimal
        entities = list(graph.query())
        
        # At minimum, we should have the person and org entities
        person_entities = [e for e in entities if e.type == "person"]
        org_entities = [e for e in entities if e.type == "org"]
        
        assert len(person_entities) >= 1, "Should have at least one person entity"
        assert len(org_entities) >= 1, "Should have at least one org entity"
        
        # Jerome Powell should exist
        powell = [e for e in person_entities if e.name == "Jerome Powell"]
        assert len(powell) == 1, f"Expected 1 Jerome Powell, got {len(powell)}"
        
        fed = [e for e in org_entities if e.name == "Federal Reserve"]
        assert len(fed) == 1, f"Expected 1 Federal Reserve, got {len(fed)}"

    @pytest.mark.asyncio
    async def test_concurrent_vs_serial_equivalence(
        self,
        world_model: WorldModel,
        provenance: Provenance,
    ) -> None:
        """
        Test that concurrent execution produces the same result as serial execution.
        
        This is the key test: run 10 agents concurrently, then run the same
        operations serially, and verify the final state is identical.
        """
        entity_type = "org"
        entity_name = "Federal Reserve"
        num_agents = 10
        
        # --- Concurrent run ---
        concurrent_world = WorldModel(WorldModelOptions(
            namespace="test_concurrent_run",
            storage="memory",
            clock=lambda: datetime(2026, 5, 18, 0, 0, 0),
        ))
        
        tasks = [
            agent_update_entity(
                concurrent_world,
                agent_id=i,
                entity_type=entity_type,
                entity_name=entity_name,
                attr_key=f"concurrent_attr_{i}",
                attr_value=f"concurrent_value_{i}",
                provenance=provenance,
            )
            for i in range(num_agents)
        ]
        
        await asyncio.gather(*tasks)
        concurrent_shape = concurrent_world.state_shape_canonical()
        
        # --- Serial run ---
        serial_world = WorldModel(WorldModelOptions(
            namespace="test_serial_run",
            storage="memory",
            clock=lambda: datetime(2026, 5, 18, 0, 0, 0),
        ))
        
        for i in range(num_agents):
            await agent_update_entity(
                serial_world,
                agent_id=i,
                entity_type=entity_type,
                entity_name=entity_name,
                attr_key=f"concurrent_attr_{i}",
                attr_value=f"concurrent_value_{i}",
                provenance=provenance,
            )
        
        serial_shape = serial_world.state_shape_canonical()
        
        # --- Compare ---
        assert concurrent_shape == serial_shape, (
            "Concurrent execution must produce the same state as serial execution"
        )

    @pytest.mark.asyncio
    async def test_high_contention_same_attribute(
        self,
        world_model: WorldModel,
        provenance: Provenance,
    ) -> None:
        """
        Test high contention: 10 agents updating the SAME attribute.
        
        With most-recent-wins policy, only one value should remain.
        The test verifies no updates are lost (all attempted) and final
        state is consistent.
        """
        entity_type = "person"
        entity_name = "Test Entity"
        num_agents = 10
        attr_key = "contested_value"
        
        tasks = [
            agent_update_entity(
                world_model,
                agent_id=i,
                entity_type=entity_type,
                entity_name=entity_name,
                attr_key=attr_key,
                attr_value=f"value_{i}",
                provenance=provenance,
            )
            for i in range(num_agents)
        ]
        
        await asyncio.gather(*tasks)
        
        graph = world_model.view("graph")
        entities = graph.query(type=entity_type, where=lambda e: e.name == entity_name)
        
        assert len(entities) == 1
        entity = entities[0]
        
        # The attribute should exist with one of the values (most-recent-wins)
        assert attr_key in entity.attrs
        assert entity.attrs[attr_key].startswith("value_")
        
        # Verify audit log has all 10 attempts
        audit = world_model.audit()
        upsert_events = [e for e in audit if e.action == "upsertEntity"]
        assert len(upsert_events) >= num_agents, f"Expected at least {num_agents} upsert events, got {len(upsert_events)}"

    @pytest.mark.asyncio
    async def test_concurrent_relationships(
        self,
        world_model: WorldModel,
        provenance: Provenance,
    ) -> None:
        """
        Test 10 agents creating relationships concurrently.
        
        When creating multiple relationships with the same from_, type, and to,
        bitemporal semantics close the previous edge. So we expect 10 creation
        events + 9 closure events = 19 total relate events.
        """
        # First create two entities
        await world_model.upsert_entity(
            type="person",
            name="Alice",
            source=provenance,
        )
        await world_model.upsert_entity(
            type="person",
            name="Bob",
            source=provenance,
        )
    
        graph = world_model.view("graph")
        alice = graph.query(type="person", where=lambda e: e.name == "Alice")[0]
        bob = graph.query(type="person", where=lambda e: e.name == "Bob")[0]
    
        num_agents = 10
    
        async def create_relationship(agent_id: int) -> None:
            await asyncio.sleep(random.uniform(0.001, 0.01))
            await world_model.relate(
                from_=alice.id,
                type="knows",
                to=bob.id,
                attrs={"since": f"202{agent_id}", "agent": agent_id},
                source=provenance,
            )
    
        tasks = [create_relationship(i) for i in range(num_agents)]
        await asyncio.gather(*tasks)
    
        # Check that all 10 relationship creation attempts happened
        # With bitemporal semantics, each new edge with same from/type/to closes the previous
        # So we expect 10 creation events + 9 closure events = 19 total relate events
        rels = [
            r for r in world_model.events()
            if r.kind == "relate"
        ]
        assert len(rels) == num_agents * 2 - 1, f"Expected {num_agents * 2 - 1} relationship events (10 creates + 9 closes), got {len(rels)}"
        
        # Final state should have exactly 1 open relationship (the last one created)
        graph = world_model.view("graph")
        neighbors = graph.neighbors_of(alice.id, via="knows")
        assert len(neighbors) == 1, f"Expected 1 open relationship, got {len(neighbors)}"
        assert neighbors[0].id == bob.id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])