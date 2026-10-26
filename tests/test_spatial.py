from __future__ import annotations

import pytest

from roadops.spatial import (
    audit_event_link_join,
    build_road_links,
    kma_grid_from_wgs84,
    normalize_link_id,
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
