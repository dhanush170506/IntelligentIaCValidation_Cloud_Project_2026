from .graph_node import GraphNode, GraphNodeError
from .graph_edge import GraphEdge, GraphEdgeError
from .resource_graph import ResourceGraph, ResourceGraphError
from .graph_builder import GraphBuilder, GraphBuilderError


def make_node(node_id, resource_type, canonical_type, name):
    return GraphNode(
        id=node_id,
        provider="Terraform",
        type=resource_type,
        canonical_type=canonical_type,
        name=name,
        properties={}
    )


def test_1_graph_node():
    node = make_node(
        "aws_instance.web_server",
        "aws_instance",
        "compute_instance",
        "web_server"
    )

    assert node.id == "aws_instance.web_server"
    assert node.provider == "Terraform"
    assert node.canonical_type == "compute_instance"

    data = node.to_dict()

    assert data["id"] == "aws_instance.web_server"
    assert data["type"] == "aws_instance"

    restored = GraphNode.from_dict(data)

    assert restored.id == node.id

    print("TEST 1 PASSED: GraphNode")


def test_2_graph_node_validation():
    try:
        GraphNode.from_dict({})
        raise AssertionError("GraphNodeError was not raised")
    except GraphNodeError:
        pass

    try:
        make_node("", "aws_instance", "compute_instance", "web_server")
        raise AssertionError("GraphNodeError was not raised")
    except GraphNodeError:
        pass

    print("TEST 2 PASSED: GraphNode validation")


def test_3_graph_edge():
    edge = GraphEdge(
        source="aws_instance.web_server",
        target="aws_security_group.web_sg",
        relationship="depends_on",
        provider="Terraform"
    )

    assert edge.source == "aws_instance.web_server"
    assert edge.target == "aws_security_group.web_sg"
    assert edge.relationship == "depends_on"

    data = edge.to_dict()

    assert data["source"] == "aws_instance.web_server"
    assert data["target"] == "aws_security_group.web_sg"

    restored = GraphEdge.from_dict(data)

    assert restored.source == edge.source
    assert restored.target == edge.target

    print("TEST 3 PASSED: GraphEdge")


def test_4_graph_edge_validation():
    try:
        GraphEdge.from_dict({})
        raise AssertionError("GraphEdgeError was not raised")
    except GraphEdgeError:
        pass

    try:
        GraphEdge(
            source="node1",
            target="node1",
            relationship="depends_on",
            provider="Terraform"
        )
        raise AssertionError("GraphEdgeError was not raised")
    except GraphEdgeError:
        pass

    print("TEST 4 PASSED: GraphEdge validation")


def test_5_resource_graph():
    graph = ResourceGraph()

    sg = make_node(
        "aws_security_group.web_sg",
        "aws_security_group",
        "security_group",
        "web_sg"
    )

    ec2 = make_node(
        "aws_instance.web_server",
        "aws_instance",
        "compute_instance",
        "web_server"
    )

    graph.add_node(sg)
    graph.add_node(ec2)

    edge = GraphEdge(
        source="aws_instance.web_server",
        target="aws_security_group.web_sg",
        relationship="depends_on",
        provider="Terraform"
    )

    graph.add_edge(edge)

    assert graph.node_count() == 2
    assert graph.edge_count() == 1

    assert graph.has_node("aws_instance.web_server")
    assert graph.has_node("aws_security_group.web_sg")

    assert graph.has_edge(
        "aws_instance.web_server",
        "aws_security_group.web_sg"
    )

    print("TEST 5 PASSED: ResourceGraph construction")


def test_6_parent_child_relationships():
    graph = ResourceGraph()

    sg = make_node(
        "aws_security_group.web_sg",
        "aws_security_group",
        "security_group",
        "web_sg"
    )

    ec2 = make_node(
        "aws_instance.web_server",
        "aws_instance",
        "compute_instance",
        "web_server"
    )

    graph.add_node(sg)
    graph.add_node(ec2)

    graph.add_edge(
        GraphEdge(
            source="aws_instance.web_server",
            target="aws_security_group.web_sg",
            relationship="depends_on",
            provider="Terraform"
        )
    )

    children = graph.get_children("aws_instance.web_server")
    parents = graph.get_parents("aws_security_group.web_sg")

    assert len(children) == 1
    assert children[0].id == "aws_security_group.web_sg"

    assert len(parents) == 1
    assert parents[0].id == "aws_instance.web_server"

    print("TEST 6 PASSED: Parent/child relationships")


def test_7_duplicate_detection():
    graph = ResourceGraph()

    node = make_node(
        "node1",
        "aws_instance",
        "compute_instance",
        "server"
    )

    graph.add_node(node)

    try:
        graph.add_node(node)
        raise AssertionError("ResourceGraphError was not raised")
    except ResourceGraphError:
        pass

    print("TEST 7 PASSED: Duplicate node detection")


def test_8_missing_node_edge():
    graph = ResourceGraph()

    graph.add_node(
        make_node(
            "node1",
            "aws_instance",
            "compute_instance",
            "server"
        )
    )

    edge = GraphEdge(
        source="node1",
        target="missing",
        relationship="depends_on",
        provider="Terraform"
    )

    try:
        graph.add_edge(edge)
        raise AssertionError("ResourceGraphError was not raised")
    except ResourceGraphError:
        pass

    print("TEST 8 PASSED: Missing-node edge detection")


def test_9_graph_serialization():
    graph = ResourceGraph()

    graph.add_node(
        make_node(
            "sg",
            "aws_security_group",
            "security_group",
            "web_sg"
        )
    )

    graph.add_node(
        make_node(
            "ec2",
            "aws_instance",
            "compute_instance",
            "web_server"
        )
    )

    graph.add_edge(
        GraphEdge(
            source="ec2",
            target="sg",
            relationship="depends_on",
            provider="Terraform"
        )
    )

    data = graph.to_dict()

    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1

    print("TEST 9 PASSED: Graph serialization")


def test_9b_graph_serialization_is_deterministic():
    graph = ResourceGraph()
    for node_id in ("a", "b", "c"):
        graph.add_node(make_node(node_id, "aws_instance", "compute_instance", node_id))
    # Insert in reverse lexical order; serialization must not depend on set order.
    graph.add_edge(GraphEdge(source="c", target="a", relationship="depends_on", provider="Terraform"))
    graph.add_edge(GraphEdge(source="b", target="a", relationship="depends_on", provider="Terraform"))
    first = graph.to_dict()
    second = graph.to_dict()
    assert first == second
    assert [edge["source"] for edge in first["edges"]] == ["b", "c"]
    print("TEST 9B PASSED: Deterministic graph serialization")


def test_10_graph_builder():
    uir = {
        "provider": "Terraform",
        "metadata": {
            "resource_count": 2,
            "dependency_count": 1
        },
        "resources": [
            {
                "id": "aws_security_group.web_sg",
                "provider": "Terraform",
                "type": "aws_security_group",
                "canonical_type": "security_group",
                "name": "web_sg",
                "properties": {}
            },
            {
                "id": "aws_instance.web_server",
                "provider": "Terraform",
                "type": "aws_instance",
                "canonical_type": "compute_instance",
                "name": "web_server",
                "properties": {}
            }
        ],
        "dependencies": [
            {
                "source": "aws_instance.web_server",
                "target": "aws_security_group.web_sg",
                "relationship": "depends_on",
                "provider": "Terraform"
            }
        ]
    }

    builder = GraphBuilder()

    graph = builder.build(uir)

    assert graph.node_count() == 2
    assert graph.edge_count() == 1

    print("TEST 10 PASSED: GraphBuilder")


def test_11_graph_builder_attach():
    uir = {
        "provider": "Terraform",
        "metadata": {},
        "resources": [
            {
                "id": "aws_security_group.web_sg",
                "provider": "Terraform",
                "type": "aws_security_group",
                "canonical_type": "security_group",
                "name": "web_sg",
                "properties": {}
            },
            {
                "id": "aws_instance.web_server",
                "provider": "Terraform",
                "type": "aws_instance",
                "canonical_type": "compute_instance",
                "name": "web_server",
                "properties": {}
            }
        ],
        "dependencies": [
            {
                "source": "aws_instance.web_server",
                "target": "aws_security_group.web_sg",
                "relationship": "depends_on",
                "provider": "Terraform"
            }
        ]
    }

    builder = GraphBuilder()

    result = builder.attach_graph(uir)

    assert "graph" in result
    assert "nodes" in result["graph"]
    assert "edges" in result["graph"]

    assert len(result["graph"]["nodes"]) == 2
    assert len(result["graph"]["edges"]) == 1

    # Ensure original UIR was not modified.
    assert "graph" not in uir

    print("TEST 11 PASSED: Graph attachment")


def test_12_unknown_dependency():
    uir = {
        "provider": "Terraform",
        "resources": [
            {
                "id": "node1",
                "provider": "Terraform",
                "type": "aws_instance",
                "canonical_type": "compute_instance",
                "name": "server",
                "properties": {}
            }
        ],
        "dependencies": [
            {
                "source": "node1",
                "target": "does_not_exist",
                "relationship": "depends_on",
                "provider": "Terraform"
            }
        ]
    }

    try:
        GraphBuilder().build(uir)
        raise AssertionError("GraphBuilderError was not raised")
    except GraphBuilderError:
        pass

    print("TEST 12 PASSED: Unknown dependency detection")


if __name__ == "__main__":
    tests = [
        test_1_graph_node,
        test_2_graph_node_validation,
        test_3_graph_edge,
        test_4_graph_edge_validation,
        test_5_resource_graph,
        test_6_parent_child_relationships,
        test_7_duplicate_detection,
        test_8_missing_node_edge,
        test_9_graph_serialization,
        test_9b_graph_serialization_is_deterministic,
        test_10_graph_builder,
        test_11_graph_builder_attach,
        test_12_unknown_dependency,
    ]

    for test in tests:
        test()

    print("\n========================================")
    print("ALL 12 GRAPH TESTS PASSED")
    print("========================================")
