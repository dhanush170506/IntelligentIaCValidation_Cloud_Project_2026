"""resource_graph.py.

Defines `ResourceGraph`, the in-memory infrastructure graph built from
the Unified Intermediate Representation (UIR).

`ResourceGraph` composes `graph_node.GraphNode` (vertices) and
`graph_edge.GraphEdge` (directed edges) into a single queryable
structure: resources indexed by id, dependency edges, and both forward
and reverse adjacency for fast child/parent lookups. It performs no
parsing, extraction, or schema validation of its own — it assumes the
`GraphNode` and `GraphEdge` instances it is given are already valid —
and instead enforces graph-level invariants (no duplicate nodes, no
duplicate edges, no edge referencing an unknown node). Later modules —
the Static Validation Engine, the Multi-Agent Framework, Runtime Drift
Analysis, and the Recommendation Engine — are expected to build
directly on this structure.

Requirements:
    - Python 3.12

Typical usage:
    from graph_node import GraphNode
    from graph_edge import GraphEdge
    from resource_graph import ResourceGraph

    graph = ResourceGraph()
    graph.add_node(GraphNode.from_dict(uir["resources"][0]))
    graph.add_node(GraphNode.from_dict(uir["resources"][1]))
    graph.add_edge(GraphEdge.from_dict(uir["dependencies"][0]))

    print(graph)
    # ResourceGraph(nodes=2, edges=1)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from .graph_edge import GraphEdge
from .graph_node import GraphNode

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

if not logger.handlers:
    # Configure a default handler only if the module is used standalone
    # (i.e. the host application hasn't already configured logging).
    _handler = logging.StreamHandler()
    _formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------
class ResourceGraphError(Exception):
    """Raised when a graph mutation would violate a graph-level invariant."""


# ---------------------------------------------------------------------------
# ResourceGraph
# ---------------------------------------------------------------------------
class ResourceGraph:
    """An in-memory, directed infrastructure resource graph.

    Nodes represent cloud resources (`GraphNode`); edges represent
    directed dependency relationships between them (`GraphEdge`).
    Forward adjacency (`outgoing_edges`) and reverse adjacency
    (`incoming_edges`) are maintained alongside the primary node and
    edge stores so that child/parent lookups do not require scanning
    every edge.

    Attributes:
        nodes: Mapping of node id to `GraphNode`.
        edges: The set of all `GraphEdge` instances in the graph.
        outgoing_edges: Mapping of a node id to the set of node ids it
            has an outgoing edge to.
        incoming_edges: Mapping of a node id to the set of node ids
            that have an outgoing edge to it.
    """

    def __init__(self) -> None:
        """Initialize an empty `ResourceGraph`."""
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Set[GraphEdge] = set()
        self.outgoing_edges: Dict[str, Set[str]] = {}
        self.incoming_edges: Dict[str, Set[str]] = {}

    def add_node(self, node: GraphNode) -> None:
        """Add a node to the graph.

        Args:
            node: The `GraphNode` to add.

        Raises:
            ResourceGraphError: If a node with the same `id` already
                exists in the graph.
        """
        if node.id in self.nodes:
            logger.error("Duplicate node id: %s", node.id)
            raise ResourceGraphError(f"Duplicate node id: {node.id}")

        self.nodes[node.id] = node
        self.outgoing_edges.setdefault(node.id, set())
        self.incoming_edges.setdefault(node.id, set())
        logger.debug("Added node: %s", node.id)

    def add_edge(self, edge: GraphEdge) -> None:
        """Add a dependency edge to the graph.

        Args:
            edge: The `GraphEdge` to add.

        Raises:
            ResourceGraphError: If `edge.source` or `edge.target` does
                not already exist as a node in the graph, or if an
                identical edge has already been added.
        """
        if edge.source not in self.nodes:
            logger.error("Cannot add edge: missing source node '%s'", edge.source)
            raise ResourceGraphError(f"Missing source node: {edge.source}")

        if edge.target not in self.nodes:
            logger.error("Cannot add edge: missing target node '%s'", edge.target)
            raise ResourceGraphError(f"Missing target node: {edge.target}")

        if edge in self.edges:
            logger.error("Duplicate edge: %r", edge)
            raise ResourceGraphError(f"Duplicate edge: {edge!r}")

        self.edges.add(edge)
        self.outgoing_edges[edge.source].add(edge.target)
        self.incoming_edges[edge.target].add(edge.source)
        logger.debug("Added edge: %s -> %s (%s)", edge.source, edge.target, edge.relationship)

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Look up a node by id.

        Args:
            node_id: The id of the node to look up.

        Returns:
            The matching `GraphNode`, or `None` if no such node exists.
        """
        return self.nodes.get(node_id)

    def has_node(self, node_id: str) -> bool:
        """Check whether a node with the given id exists in the graph.

        Args:
            node_id: The node id to check.

        Returns:
            True if a node with this id exists, False otherwise.
        """
        return node_id in self.nodes

    def has_edge(self, source: str, target: str) -> bool:
        """Check whether a direct edge exists from `source` to `target`.

        Args:
            source: The source node id.
            target: The target node id.

        Returns:
            True if an edge from `source` to `target` exists, False
            otherwise (including if either node does not exist).
        """
        return target in self.outgoing_edges.get(source, set())

    def get_children(self, node_id: str) -> List[GraphNode]:
        """Get every node that `node_id` has an outgoing edge to.

        Args:
            node_id: The id of the node whose children to retrieve.

        Returns:
            A list of `GraphNode` instances. Empty if `node_id` has no
            outgoing edges or does not exist in the graph.
        """
        child_ids = self.outgoing_edges.get(node_id, set())
        return [self.nodes[child_id] for child_id in sorted(child_ids)]

    def get_parents(self, node_id: str) -> List[GraphNode]:
        """Get every node that has an outgoing edge to `node_id`.

        Args:
            node_id: The id of the node whose parents to retrieve.

        Returns:
            A list of `GraphNode` instances. Empty if `node_id` has no
            incoming edges or does not exist in the graph.
        """
        parent_ids = self.incoming_edges.get(node_id, set())
        return [self.nodes[parent_id] for parent_id in sorted(parent_ids)]

    def get_all_nodes(self) -> List[GraphNode]:
        """Get every node in the graph.

        Returns:
            A list of all `GraphNode` instances, in insertion order.
        """
        return list(self.nodes.values())

    def get_all_edges(self) -> List[GraphEdge]:
        """Get every edge in the graph.

        Returns:
            A list of all `GraphEdge` instances.
        """
        return sorted(
            self.edges,
            key=lambda edge: (edge.source, edge.target, edge.relationship, edge.provider),
        )

    def node_count(self) -> int:
        """Count the nodes in the graph.

        Returns:
            The number of nodes currently in the graph.
        """
        return len(self.nodes)

    def edge_count(self) -> int:
        """Count the edges in the graph.

        Returns:
            The number of edges currently in the graph.
        """
        return len(self.edges)

    def to_dict(self) -> Dict[str, List[Dict[str, Any]]]:
        """Convert this graph into a plain, JSON-serializable dictionary.

        Returns:
            A dictionary with the shape:
                {
                    "nodes": [GraphNode.to_dict(), ...],
                    "edges": [GraphEdge.to_dict(), ...]
                }
        """
        return {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.get_all_edges()],
        }

    def __contains__(self, node_id: str) -> bool:
        """Support `"node_id" in graph` membership checks.

        Args:
            node_id: The node id to check.

        Returns:
            True if a node with this id exists in the graph, False
            otherwise.
        """
        return node_id in self.nodes

    def __len__(self) -> int:
        """Support `len(graph)`.

        Returns:
            The number of nodes in the graph.
        """
        return len(self.nodes)

    def __repr__(self) -> str:
        """Return a short, readable representation for debugging.

        Returns:
            A string of the form "ResourceGraph(nodes=N, edges=M)".
        """
        return f"ResourceGraph(nodes={len(self.nodes)}, edges={len(self.edges)})"


# `Graph` is exported as a convenience alias for `ResourceGraph`, so
# later modules may refer to either name.
Graph = ResourceGraph


__all__ = [
    "Graph",
    "ResourceGraph",
    "ResourceGraphError",
]
