from __future__ import annotations

import zipfile
from pathlib import Path

import shapefile
from pyproj import CRS

from roadops.nodelink import extract_jeju_nodelink
from roadops.quality import load_records, profile_road_network


def _write_fixture_archive(root: Path) -> Path:
    source_dir = root / "source"
    source_dir.mkdir()

    node_base = source_dir / "MOCT_NODE"
    with shapefile.Writer(str(node_base), shapeType=shapefile.POINT, encoding="utf-8") as writer:
        writer.field("NODE_ID", "C", size=10)
        writer.field("NODE_NAME", "C", size=40)
        writer.point(126.8327, 33.3260)
        writer.record("4080000001", "제주 시작")
        writer.point(126.8337, 33.3270)
        writer.record("4080000002", "제주 종료")
        writer.point(126.9780, 37.5665)
        writer.record("1000000001", "서울")

    link_base = source_dir / "MOCT_LINK"
    with shapefile.Writer(str(link_base), shapeType=shapefile.POLYLINE, encoding="utf-8") as writer:
        writer.field("LINK_ID", "C", size=10)
        writer.field("F_NODE", "C", size=10)
        writer.field("T_NODE", "C", size=10)
        writer.field("ROAD_NAME", "C", size=40)
        writer.field("ROAD_RANK", "C", size=3)
        writer.field("ROAD_NO", "C", size=5)
        writer.field("LANES", "N", size=2)
        writer.field("MAX_SPD", "N", size=3)
        writer.field("ROAD_TYPE", "C", size=3)
        writer.line([[(126.8327, 33.3260), (126.8337, 33.3270)]])
        writer.record(
            "4050000001", "4080000001", "4080000002", "제주로", "107", "", 2, 50, "000"
        )
        writer.line([[(126.8337, 33.3270), (126.9780, 37.5665)]])
        writer.record(
            "4050000002", "4080000002", "1000000001", "제외도로", "107", "", 2, 50, "000"
        )

    projection = CRS.from_epsg(4326).to_wkt()
    for base in (node_base, link_base):
        base.with_suffix(".prj").write_text(projection, encoding="utf-8")
        base.with_suffix(".cpg").write_text("UTF-8", encoding="ascii")

    archive_path = root / "nodelink.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in source_dir.iterdir():
            archive.write(path, arcname=path.name)
    return archive_path


def test_extract_jeju_nodelink_and_run_quality_profile(tmp_path):
    archive = _write_fixture_archive(tmp_path)
    output_dir = tmp_path / "output"

    manifest = extract_jeju_nodelink(
        archive,
        extract_dir=tmp_path / "extracted",
        output_dir=output_dir,
    )
    nodes = load_records(output_dir / "jeju_nodes.csv")
    links = load_records(output_dir / "jeju_links.csv")
    report = profile_road_network(links, nodes)

    assert manifest["node_rows"] == 2
    assert manifest["link_rows"] == 1
    assert manifest["source_node_records"] == 3
    assert manifest["source_link_records"] == 2
    assert manifest["links_with_one_jeju_endpoint"] == 1
    assert manifest["target_crs"] == "EPSG:4326"
    assert links[0]["link_id"] == "4050000001"
    assert links[0]["road_number"] == ""
    assert links[0]["geometry_wkt"].startswith("LINESTRING")
    assert report["status"] == "pass"
