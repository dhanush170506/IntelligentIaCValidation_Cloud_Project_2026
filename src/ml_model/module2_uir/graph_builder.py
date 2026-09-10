"""graph_builder.py.

Constructs a `resource_graph.ResourceGraph` from a Unified
Intermediate Representation (UIR) and, conversely, serializes a
constructed graph back into a `graph` section that can be embedded
into a UIR.

`GraphBuilder` is the single seam between the UIR's flat dictionary
representation (`resources`, `dependencies`) and the typed, queryable
graph representation (`GraphNode`, `GraphEdge`, `ResourceGraph`) that
later modules — the Static Validation Engine, the Multi-Agent
Framework, Runtime Drift Analysis, and the Recommendation Engine — are
expected to consume. It performs no UIR schema validation itself
(that is `uir_validator.validate_uir()`'s responsibility); it only
translates already-shaped resource and dependency records into graph
objects, and surfaces every failure along the way as a single,
consistent `GraphBuilderError`.

Requirements:
    - Python 3.12

Typical usage:
    from graph_builder import GraphBuilder

    builder = GraphBuilder()
    graph = builder.build(uir)
    uir_with_graph = builder.attach_graph(uir)
    graph_section_only = builder.build_graph_only(uir)
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .graph_edge import GraphEdge, GraphEdgeError
from .graph_node import GraphNode, GraphNodeError
from .resource_graph import ResourceGraph, ResourceGraphError

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
class GraphBuilderError(Exception):
    """Raised when a `ResourceGraph` cannot be built from a UIR.

    Every failure this module can encounter — a missing top-level UIR
    field, a resource missing its `id`, a duplicate node, a dependency
    referencing an unknown resource, or any other malformed-graph
    condition surfaced by `GraphNode`, `GraphEdge`, or `ResourceGraph`
    — is normalized into this single exception type, so callers of
    `GraphBuilder` only ever need to handle one error.
    """


# ---------------------------------------------------------------------------
# Required top-level UIR keys this module depends on.
# ---------------------------------------------------------------------------
_KEY_RESOURCES = "resources"
_KEY_DEPENDENCIES = "dependencies"
_KEY_GRAPH = "graph"


# ---------------------------------------------------------------------------
# GraphBuilder
# ---------------------------------------------------------------------------
class GraphBuilder:
    """Builds a `ResourceGraph` from a UIR, and serializes it back.

    `GraphBuilder` holds no state between calls; each public method
    operates only on the UIR dictionary it is given.
    """

    def build(self, uir: Dict[str, Any]) -> ResourceGraph:
        """Construct a `ResourceGraph` from a UIR.

        Every entry in `uir["resources"]` is converted to a
        `GraphNode` (via `GraphNode.from_dict()`) and inserted into a
        new `ResourceGraph`; every entry in `uir["dependencies"]` is
        then converted to a `GraphEdge` (via `GraphEdge.from_dict()`)
        and inserted the same way. Nodes are inserted before edges so
        that an edge's source and target are guaranteed to already
        exist by the time it is added.

        Args:
            uir: The UIR dictionary to build a graph from. Must contain
                `resources` and `dependencies` keys.

        Returns:
            A `ResourceGraph` populated with every resource and
            dependency from `uir`.

        Raises:
            GraphBuilderError: If `uir` is not a dict, is missing
                `resources` or `dependencies`, if any resource is
                missing its `id` (or otherwise fails `GraphNode`
                validation), if two resources share the same `id`, if
                any dependency references a resource that was not
                present in `resources` (or otherwise fails `GraphEdge`
                validation), or if any other graph-level invariant is
                violated.
        """
        logger.info("Starting graph construction.")

        if not isinstance(uir, dict):
            logger.error("Graph construction failed: expected a dict, got %s", type(uir).__name__)
            raise GraphBuilderError(f"Expected a dict, got {type(uir).__name__}")

        if _KEY_RESOURCES not in uir:
            logger.error("Graph construction failed: UIR is missing '%s'", _KEY_RESOURCES)
            raise GraphBuilderError(f"UIR is missing required field: '{_KEY_RESOURCES}'")

        if _KEY_DEPENDENCIES not in uir:
            logger.error("Graph construction failed: UIR is missing '%s'", _KEY_DEPENDENCIES)
            raise GraphBuilderError(f"UIR is missing required field: '{_KEY_DEPENDENCIES}'")

        graph = ResourceGraph()

        for index, resource in enumerate(uir[_KEY_RESOURCES]):
            self._add_node_from_resource(graph, resource, index)

        for index, dependency in enumerate(uir[_KEY_DEPENDENCIES]):
            self._add_edge_from_dependency(graph, dependency, index)

        logger.info(
            "Graph construction complete: nodes=%d, edges=%d",
            graph.node_count(),
            graph.edge_count(),
        )
        return graph

    def attach_graph(self, uir: Dict[str, Any]) -> Dict[str, Any]:
        """Build a graph from a UIR and embed it back into the UIR.

        Args:
            uir: The UIR dictionary to build a graph from and attach
                the result to.

        Returns:
            A new dictionary containing every key from `uir` plus a
            `graph` key holding `ResourceGraph.to_dict()`:
                {
                    "provider": ...,
                    "metadata": ...,
                    "resources": ...,
                    "dependencies": ...,
                    "graph": {"nodes": [...], "edges": [...]}
                }
            `uir` itself is left unmodified.

        Raises:
            GraphBuilderError: Under the same conditions as `build()`.
        """
        graph = self.build(uir)

        uir_with_graph = dict(uir)
        uir_with_graph[_KEY_GRAPH] = graph.to_dict()

        logger.info("Attached graph section to UIR.")
        return uir_with_graph

    def build_graph_only(self, uir: Dict[str, Any]) -> Dict[str, Any]:
        """Build a graph from a UIR and return only its serialized form.

        Args:
            uir: The UIR dictionary to build a graph from.

        Returns:
            `ResourceGraph.to_dict()`:
                {"nodes": [...], "edges": [...]}

        Raises:
            GraphBuilderError: Under the same conditions as `build()`.
        """
        graph = self.build(uir)
        return graph.to_dict()

    @staticmethod
    def _add_node_from_resource(graph: ResourceGraph, resource: Any, index: int) -> None:
        """Convert one resource entry into a `GraphNode` and insert it.

        Args:
            graph: The `ResourceGraph` being constructed.
            resource: The resource dictionary to convert.
            index: The resource's position in `uir["resources"]`, used
                only for error messages.

        Raises:
            GraphBuilderError: If `resource` fails `GraphNode`
                validation (e.g. a missing or empty `id`), or if a node
                with the same `id` was already added.
        """
        try:
            node = GraphNode.from_dict(resource)
        except GraphNodeError as exc:
            logger.error("Failed to build node at resources[%d]: %s", index, exc)
            raise GraphBuilderError(f"Failed to build node at resources[{index}]: {exc}") from exc

        try:
            graph.add_node(node)
        except ResourceGraphError as exc:
            logger.error("Failed to add node at resources[%d]: %s", index, exc)
            raise GraphBuilderError(f"Failed to add node at resources[{index}]: {exc}") from exc

    @staticmethod
    def _add_edge_from_dependency(graph: ResourceGraph, dependency: Any, index: int) -> None:
        """Convert one dependency entry into a `GraphEdge` and insert it.

        Args:
            graph: The `ResourceGraph` being constructed.
            dependency: The dependency dictionary to convert.
            index: The dependency's position in `uir["dependencies"]`,
                used only for error messages.

        Raises:
            GraphBuilderError: If `dependency` fails `GraphEdge`
                validation, if its `source` or `target` does not
                reference a resource already added to `graph`, or if an
                identical edge was already added.
        """
        try:
            edge = GraphEdge.from_dict(dependency)
        except GraphEdgeError as exc:
            logger.error("Failed to build edge at dependencies[%d]: %s", index, exc)
            raise GraphBuilderError(
                f"Failed to build edge at dependencies[{index}]: {exc}"
            ) from exc

        try:
            graph.add_edge(edge)
        except ResourceGraphError as exc:
            logger.error("Failed to add edge at dependencies[%d]: %s", index, exc)
            raise GraphBuilderError(f"Failed to add edge at dependencies[{index}]: {exc}") from exc


__all__ = [
    "GraphBuilder",
    "GraphBuilderError",
]
