from __future__ import annotations

from roadops.quality import load_records, profile_road_network


def healthy_network():
    nodes = [
        {"node_id": "4080000001", "latitude": 33.3260, "longitude": 126.8327},
        {"node_id": "4080000002", "latitude": 33.3270, "longitude": 126.8337},
        {"node_id": "4080000003", "latitude": 33.3280, "longitude": 126.8347},
    ]
    links = [
        {
            "link_id": "4050000001",
            "f_node": "4080000001",
            "t_node": "4080000002",
            "road_name": "제주로",
            "lane_count": 2,
            "maximum_speed_limit": 50,
            "geometry_wkt": "LINESTRING (126.8327 33.3260,126.8337 33.3270)",
        },
        {
            "link_id": "4050000002",
            "f_node": "4080000002",
            "t_node": "4080000003",
            "road_name": "제주로",
            "lane_count": 2,
            "maximum_speed_limit": 50,
            "geometry_wkt": "LINESTRING (126.8337 33.3270,126.8347 33.3280)",
        },
    ]
    return links, nodes


def test_healthy_road_network_passes_all_gates():
    links, nodes = healthy_network()

    report = profile_road_network(links, nodes)

    assert report["status"] == "pass"
    assert report["failed_checks"] == []
    assert report["summary"]["built_link_geometries"] == 2
    assert report["summary"]["connected_components"] == 1
    assert report["summary"]["isolated_nodes"] == 0
    assert all(check["passed"] for check in report["checks"])


def test_profile_reports_duplicates_orphans_invalid_coordinates_and_self_loops():
    links = [
        {"link_id": "4050000001", "f_node": "4080000001", "t_node": "4080000999"},
        {"link_id": "4050000001", "f_node": "4080000001", "t_node": "4080000001"},
        {"link_id": "bad", "f_node": "bad", "t_node": "4080000002"},
    ]
    nodes = [
        {"node_id": "4080000001", "latitude": 33.3260, "longitude": 126.8327},
        {"node_id": "4080000001", "latitude": 33.3261, "longitude": 126.8328},
        {"node_id": "4080000002", "latitude": 0, "longitude": 0},
    ]

    report = profile_road_network(links, nodes)

    assert report["status"] == "fail"
    assert report["summary"]["duplicate_node_row_excess"] == 1
    assert report["summary"]["duplicate_link_row_excess"] == 1
    assert report["summary"]["orphan_endpoint_references"] == 1
    assert report["summary"]["self_loop_links"] == 1
    assert report["issue_counts"]["invalid_node_coordinate"] == 1
    assert "link_node_referential_integrity" in report["failed_checks"]


def test_empty_inputs_fail_instead_of_reporting_perfect_quality():
    report = profile_road_network([], [])

    assert report["status"] == "fail"
    assert all(check["observed_rate"] is None for check in report["checks"])


def test_load_records_accepts_cp949_csv(tmp_path):
    path = tmp_path / "nodes.csv"
    path.write_bytes("node_id,latitude,longitude,이름\n4080000001,33.3,126.8,제주\n".encode("cp949"))

    rows = load_records(path)

    assert rows[0]["node_id"] == "4080000001"
    assert rows[0]["이름"] == "제주"


def test_issue_sample_limit_does_not_hide_total_counts():
    links = [{"link_id": "bad", "f_node": "bad", "t_node": "bad"} for _ in range(5)]

    report = profile_road_network(links, [], issue_sample_limit=2)

    assert len(report["issue_sample"]) == 2
    assert report["issue_sample_truncated"] is True
    assert report["issue_counts"]["invalid_link_id"] == 5


def test_attribute_and_connectivity_gates_detect_routing_risks():
    links, nodes = healthy_network()
    links[0]["road_name"] = "-"
    links[0]["lane_count"] = 0
    links[0]["maximum_speed_limit"] = "unknown"
    links[0]["geometry_wkt"] = "POINT (126.8 33.3)"
    links.pop()

    report = profile_road_network(links, nodes)

    assert report["status"] == "fail"
    assert report["summary"]["connected_components"] == 2
    assert report["summary"]["isolated_nodes"] == 1
    assert "lane_count_validity" in report["failed_checks"]
    assert "maximum_speed_limit_validity" in report["failed_checks"]
    assert "source_geometry_validity" in report["failed_checks"]
    assert "largest_connected_component_share" in report["failed_checks"]
