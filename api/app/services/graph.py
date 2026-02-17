"""Higher-level graph analytics built on top of the Neo4j driver wrapper."""

from __future__ import annotations

from typing import Any

from app.db.neo4j import GraphDB


class GraphService:
    """Analytical graph operations — pathfinding, ripple tracing, clustering.

    Each method translates a domain question into one or more Cypher queries
    and returns a structure ready for the API layer.
    """

    def __init__(self, graph: GraphDB) -> None:
        self._graph = graph

    # ------------------------------------------------------------------
    # Shortest path
    # ------------------------------------------------------------------

    async def find_shortest_path(
        self,
        from_id: str,
        to_id: str,
        max_depth: int = 6,
    ) -> dict[str, Any] | None:
        """Return the shortest undirected path between two entity nodes.

        Returns a dict with ``nodes`` (ordered list) and ``edges`` (connecting
        relationships), or *None* if no path exists within *max_depth* hops.
        """
        query = """
        MATCH (start {id: $from_id}), (end {id: $to_id}),
              path = shortestPath((start)-[*..{max_depth}]-(end))
        WITH path
        RETURN [n IN nodes(path) | n{.*, _labels: labels(n)}]  AS nodes,
               [r IN relationships(path) | {
                   type: type(r),
                   from: startNode(r).id,
                   to:   endNode(r).id,
                   props: properties(r)
               }] AS edges,
               length(path) AS hops
        """.replace("{max_depth}", str(max_depth))

        rows = await self._graph.execute(
            query, {"from_id": from_id, "to_id": to_id}
        )
        if not rows:
            return None

        row = rows[0]
        return {
            "from_id": from_id,
            "to_id": to_id,
            "hops": row["hops"],
            "nodes": row["nodes"],
            "edges": row["edges"],
        }

    # ------------------------------------------------------------------
    # Entity network (subgraph)
    # ------------------------------------------------------------------

    async def get_entity_network(
        self,
        entity_id: str,
        depth: int = 2,
    ) -> dict[str, Any]:
        """Return the full subgraph around an entity up to *depth* hops.

        The result contains deduplicated ``nodes`` and ``edges`` suitable for
        a force-directed graph visualisation.
        """
        query = """
        MATCH path = (center {id: $entity_id})-[*1..{depth}]-(connected)
        WITH center, path
        UNWIND nodes(path) AS n
        WITH DISTINCT n,
             collect(DISTINCT relationships(path)) AS all_rels_nested
        UNWIND all_rels_nested AS rel_list
        UNWIND rel_list AS r
        WITH collect(DISTINCT n{.*, _labels: labels(n)}) AS nodes,
             collect(DISTINCT {
                 type: type(r),
                 from: startNode(r).id,
                 to:   endNode(r).id,
                 props: properties(r)
             }) AS edges
        RETURN nodes, edges
        """.replace("{depth}", str(depth))

        rows = await self._graph.execute(query, {"entity_id": entity_id})

        if not rows:
            # Entity might exist but have zero connections
            entity = await self._graph.find_entity(entity_id)
            return {
                "nodes": [entity] if entity else [],
                "edges": [],
            }

        return {
            "nodes": rows[0]["nodes"],
            "edges": rows[0]["edges"],
        }

    # ------------------------------------------------------------------
    # Ripple trace (event propagation)
    # ------------------------------------------------------------------

    async def get_ripple_trace(
        self,
        event_id: str,
        max_hops: int = 3,
    ) -> dict[str, Any] | None:
        """Trace outward from an Event node through connected entities and events.

        Returns concentric "rings" — each ring is one hop further from the
        origin event.  This powers the ripple-map visualisation.
        """
        # Verify the event exists
        check = await self._graph.execute(
            "MATCH (ev:Event {id: $eid}) RETURN ev{.*, _labels: labels(ev)} AS event",
            {"eid": event_id},
        )
        if not check:
            return None

        origin = check[0]["event"]

        rings: list[list[dict[str, Any]]] = []
        edges: list[dict[str, Any]] = []

        for hop in range(1, max_hops + 1):
            query = f"""
            MATCH (ev:Event {{id: $eid}})-[r*{hop}..{hop}]-(n)
            WITH DISTINCT n, r
            RETURN n{{.*, _labels: labels(n)}} AS node,
                   [rel IN r | {{
                       type: type(rel),
                       from: startNode(rel).id,
                       to:   endNode(rel).id
                   }}] AS rels
            """
            rows = await self._graph.execute(query, {"eid": event_id})
            ring_nodes: list[dict[str, Any]] = []
            for row in rows:
                ring_nodes.append(row["node"])
                edges.extend(row.get("rels", []))
            rings.append(ring_nodes)

        # Deduplicate edges by (from, to, type)
        seen_edges: set[tuple[str, str, str]] = set()
        unique_edges: list[dict[str, Any]] = []
        for e in edges:
            key = (e.get("from", ""), e.get("to", ""), e.get("type", ""))
            if key not in seen_edges:
                seen_edges.add(key)
                unique_edges.append(e)

        return {
            "origin": origin,
            "max_hops": max_hops,
            "rings": rings,
            "edges": unique_edges,
            "total_nodes": sum(len(ring) for ring in rings),
        }

    # ------------------------------------------------------------------
    # Area cluster (geographic)
    # ------------------------------------------------------------------

    async def get_area_cluster(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50,
    ) -> dict[str, Any]:
        """Return entities and events located near a geographic point.

        This query relies on ``latitude`` and ``longitude`` properties being
        stored on Location and Event nodes.  It uses the Haversine formula
        in Cypher to approximate distance filtering.
        """
        # Haversine distance approximation in Cypher
        query = """
        MATCH (n)
        WHERE (n:Location OR n:Event)
          AND n.latitude IS NOT NULL
          AND n.longitude IS NOT NULL
        WITH n,
             point({latitude: n.latitude, longitude: n.longitude}) AS p1,
             point({latitude: $lat, longitude: $lon}) AS p2
        WITH n, point.distance(p1, p2) / 1000.0 AS dist_km
        WHERE dist_km <= $radius
        RETURN n{.*, _labels: labels(n)} AS node, dist_km
        ORDER BY dist_km
        LIMIT 200
        """
        rows = await self._graph.execute(
            query, {"lat": lat, "lon": lon, "radius": radius_km}
        )

        entities: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []

        for row in rows:
            node = row["node"]
            node["distance_km"] = round(row["dist_km"], 2)
            labels = node.get("_labels", [])
            if "Event" in labels:
                events.append(node)
            else:
                entities.append(node)

        return {
            "entities": entities,
            "events": events,
            "total_entities": len(entities),
            "total_events": len(events),
        }
