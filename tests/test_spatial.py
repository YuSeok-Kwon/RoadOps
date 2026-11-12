from __future__ import annotations

import pytest

from roadops.spatial import (
    audit_event_link_join,
    build_road_links,
    kma_grid_from_wgs84,
    normalize_link_id,
    parse_link_geometry_wkt,
    point_to_link_distance_meters,
    taas_linestring,
)


def sample_network():
    nodes = [
        {"node_id": "4080000001", "latitude": 33.3260, "longitude": 126.8327},
        {"node_id": "4080000002", "latitude": 33.3270, "longitude": 126.8337},
        {"node_id": "4080000003", "latitude": 33.3280, "longitude": 126.8347},
    ]
    links = [
        {
            "link_id": "4050000001",
            "start_node_id": "4080000001",
            "end_node_id": "4080000002",
        },
        {
            "link_id": "4050000002",
            "start_node_id": "4080000002",
            "end_node_id": "4080000003",
        },
    ]
    return build_road_links(links, nodes)


def test_normalize_link_id_rejects_guessed_or_malformed_values():
    assert normalize_link_id("4050000001") == "4050000001"
    assert normalize_link_id(4050000001) == "4050000001"
    assert normalize_link_id("4050000001.0") == "4050000001"
    assert normalize_link_id("405000001") is None
    assert normalize_link_id("4050A00001") is None


def test_build_links_and_exact_event_join():
    links, issues = sample_network()
    assert not issues

    audit = audit_event_link_join(
        [{"link_id": "4050000001", "latitude": 0, "longitude": 0}], links
    )

    assert audit.exact_matches == 1
    assert audit.spatial_matches == 0
    assert audit.matches[0].method == "exact_link_id"


def test_spatial_fallback_remains_visible_in_audit():
    links, _ = sample_network()
    audit = audit_event_link_join(
        [{"link_id": "9999999999", "latitude": 33.3265, "longitude": 126.8332}],
        links,
        spatial_fallback_threshold_meters=100,
    )

    assert audit.exact_matches == 0
    assert audit.spatial_matches == 1
    assert audit.matches[0].matched_link_id == "4050000001"
    assert audit.matches[0].method == "spatial_fallback"
    assert audit.matches[0].coordinate_consistent is True


def test_full_linestring_geometry_is_used_instead_of_endpoint_chord():
    nodes = [
        {"node_id": "4080000001", "latitude": 33.3260, "longitude": 126.8327},
        {"node_id": "4080000002", "latitude": 33.3260, "longitude": 126.8347},
    ]
    links, issues = build_road_links(
        [
            {
                "link_id": "4050000001",
                "start_node_id": "4080000001",
                "end_node_id": "4080000002",
                "geometry_wkt": (
                    "LINESTRING (126.8327 33.3260,126.8337 33.3270,"
                    "126.8347 33.3260)"
                ),
            }
        ],
        nodes,
    )

    assert not issues
    point = parse_link_geometry_wkt("LINESTRING (126.8337 33.3270,126.8340 33.3270)")[0][0]
    assert point_to_link_distance_meters(point, links["4050000001"]) < 0.001


def test_multilinestring_geometry_is_parsed():
    parts = parse_link_geometry_wkt(
        "MULTILINESTRING ((126.8327 33.3260,126.8337 33.3270),"
        "(126.8337 33.3270,126.8347 33.3280))"
    )

    assert parts is not None
    assert len(parts) == 2
    assert tuple(len(part) for part in parts) == (2, 2)


def test_invalid_wkt_is_audited_and_falls_back_to_endpoints():
    nodes = [
        {"node_id": "4080000001", "latitude": 33.3260, "longitude": 126.8327},
        {"node_id": "4080000002", "latitude": 33.3270, "longitude": 126.8337},
    ]
    links, issues = build_road_links(
        [
            {
                "link_id": "4050000001",
                "start_node_id": "4080000001",
                "end_node_id": "4080000002",
                "geometry_wkt": "LINESTRING invalid",
            }
        ],
        nodes,
    )

    assert links["4050000001"].geometry_parts
    assert issues == [
        {
            "record_type": "link",
            "row_index": 0,
            "reason": "invalid_geometry_wkt_fallback_to_endpoints",
            "link_id": "4050000001",
        }
    ]


def test_near_tied_spatial_candidates_are_not_forced_to_one_link():
    nodes = [
        {"node_id": "4080000001", "latitude": 33.3260, "longitude": 126.8327},
        {"node_id": "4080000002", "latitude": 33.3270, "longitude": 126.8337},
        {"node_id": "4080000003", "latitude": 33.3260, "longitude": 126.8328},
        {"node_id": "4080000004", "latitude": 33.3270, "longitude": 126.8338},
    ]
    links, _ = build_road_links(
        [
            {
                "link_id": "4050000001",
                "start_node_id": "4080000001",
                "end_node_id": "4080000002",
            },
            {
                "link_id": "4050000002",
                "start_node_id": "4080000003",
                "end_node_id": "4080000004",
            },
        ],
        nodes,
    )

    audit = audit_event_link_join(
        [{"link_id": "-1", "latitude": 33.3265, "longitude": 126.83325}],
        links,
        spatial_fallback_threshold_meters=30,
        spatial_fallback_min_margin_meters=5,
    )

    assert audit.ambiguous_events == 1
    assert audit.spatial_matches == 0
    assert audit.matches[0].method == "ambiguous"
    assert audit.matches[0].matched_link_id is None
    assert audit.matches[0].candidate_count_within_threshold == 2
    assert audit.matches[0].nearest_candidate_link_id in links
    assert audit.matches[0].second_nearest_link_id in links


def test_far_event_is_not_forced_onto_a_link():
    links, _ = sample_network()
    audit = audit_event_link_join(
        [{"latitude": 33.55, "longitude": 126.20}],
        links,
        spatial_fallback_threshold_meters=100,
    )

    assert audit.unmatched_events == 1
    assert audit.matches[0].matched_link_id is None


def test_negative_spatial_threshold_is_rejected():
    links, _ = sample_network()
    with pytest.raises(ValueError, match="must be non-negative"):
        audit_event_link_join([], links, spatial_fallback_threshold_meters=-1)


def test_negative_margin_and_exact_coordinate_thresholds_are_rejected():
    links, _ = sample_network()
    with pytest.raises(ValueError, match="min_margin"):
        audit_event_link_join([], links, spatial_fallback_min_margin_meters=-1)
    with pytest.raises(ValueError, match="exact_coordinate"):
        audit_event_link_join([], links, exact_coordinate_threshold_meters=-1)


def test_exact_id_coordinate_conflict_is_visible_but_id_match_is_retained():
    links, _ = sample_network()
    audit = audit_event_link_join(
        [{"link_id": "4050000001", "latitude": 33.55, "longitude": 126.20}],
        links,
        exact_coordinate_threshold_meters=30,
    )

    assert audit.exact_matches == 1
    assert audit.coordinate_conflicts == 1
    assert audit.to_dict()["scoring_eligible_events"] == 0
    assert audit.matches[0].coordinate_consistent is False
    assert audit.matches[0].reason == "coordinate_exceeds_exact_link_threshold"
    assert audit.matches[0].nearest_candidate_link_id is not None
    assert audit.matches[0].nearest_candidate_distance_meters is not None


def test_exact_id_with_supplied_invalid_coordinate_is_excluded_from_scoring():
    links, _ = sample_network()
    audit = audit_event_link_join(
        [{"link_id": "4050000001", "latitude": 90.0, "longitude": 180.0}],
        links,
    )

    assert audit.exact_matches == 1
    assert audit.coordinate_conflicts == 1
    assert audit.to_dict()["scoring_eligible_events"] == 0
    assert audit.matches[0].coordinate_consistent is False
    assert audit.matches[0].reason == "invalid_coordinate_for_exact_link"


def test_taas_linestring_uses_longitude_latitude_order():
    links, _ = sample_network()
    assert taas_linestring(links["4050000001"]) == (
        "LineString(126.83270000 33.32600000,126.83370000 33.32700000)"
    )


def test_kma_grid_conversion_for_seoul_reference_point():
    assert kma_grid_from_wgs84(37.5665, 126.9780) == (60, 127)


def test_kma_grid_conversion_places_jeju_sample_in_valid_grid():
    x, y = kma_grid_from_wgs84(33.3260317412202, 126.832743354717)
    assert (x, y) == (58, 34)


def test_broad_jeju_bounds_include_chuja_islands():
    links, issues = build_road_links(
        [
            {
                "link_id": "4050000001",
                "start_node_id": "4080000001",
                "end_node_id": "4080000002",
            }
        ],
        [
            {"node_id": "4080000001", "latitude": 33.95, "longitude": 126.30},
            {"node_id": "4080000002", "latitude": 33.96, "longitude": 126.31},
        ],
    )

    assert not issues
    assert "4050000001" in links
