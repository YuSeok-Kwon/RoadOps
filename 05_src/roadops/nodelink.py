"""Extract a Jeju subset from the national standard node-link archive.

국가표준 노드링크 SHP에서 제주 노드와 링크를 재현 가능하게 추출합니다.
"""

from __future__ import annotations

import csv
import shutil
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping

import shapefile
from pyproj import CRS, Transformer

from roadops.quality import file_sha256
from roadops.spatial import parse_point


REQUIRED_SHAPEFILE_SUFFIXES = {".shp", ".shx", ".dbf", ".prj"}


def _select_shapefile_stem(names: Iterable[str], token: str) -> str:
    stems = {
        str(Path(name).with_suffix(""))
        for name in names
        if Path(name).suffix.lower() == ".shp"
        and token.upper() in Path(name).stem.upper()
        and "__MACOSX" not in name
    }
    if not stems:
        raise ValueError(f"No {token} shapefile found in archive")
    exact = [stem for stem in stems if Path(stem).name.upper() == f"MOCT_{token.upper()}"]
    if len(exact) == 1:
        return exact[0]
    if len(stems) == 1:
        return next(iter(stems))
    raise ValueError(f"Ambiguous {token} shapefiles: {sorted(stems)}")


def _extract_shapefile_group(
    archive: zipfile.ZipFile, stem: str, target_dir: Path
) -> dict[str, Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    selected: dict[str, Path] = {}
    for member in archive.namelist():
        if str(Path(member).with_suffix("")) != stem:
            continue
        suffix = Path(member).suffix.lower()
        if suffix not in REQUIRED_SHAPEFILE_SUFFIXES | {".cpg"}:
            continue
        target = target_dir / f"{Path(stem).name}{suffix}"
        with archive.open(member) as source, target.open("wb") as destination:
            shutil.copyfileobj(source, destination)
        selected[suffix] = target

    missing = REQUIRED_SHAPEFILE_SUFFIXES - selected.keys()
    if missing:
        raise ValueError(f"Incomplete shapefile group {stem}; missing {sorted(missing)}")
    return selected


def _dbf_encoding(files: Mapping[str, Path]) -> str:
    cpg = files.get(".cpg")
    if cpg is None:
        return "cp949"
    label = cpg.read_text(encoding="ascii", errors="ignore").strip().lower()
    aliases = {
        "949": "cp949",
        "ansi 949": "cp949",
        "euc-kr": "cp949",
        "utf-8": "utf-8",
        "utf8": "utf-8",
    }
    return aliases.get(label, label or "cp949")


def _reader(files: Mapping[str, Path]) -> shapefile.Reader:
    return shapefile.Reader(
        shp=str(files[".shp"]),
        shx=str(files[".shx"]),
        dbf=str(files[".dbf"]),
        encoding=_dbf_encoding(files),
        encodingErrors="replace",
    )


def _row(record: shapefile._Record) -> dict[str, Any]:
    return {str(key).strip().lower(): value for key, value in record.as_dict().items()}


def _pick(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _wkt(shape: shapefile.Shape, transformer: Transformer) -> str:
    points = [transformer.transform(x, y) for x, y, *_ in shape.points]
    if not points:
        return ""
    starts = list(shape.parts) + [len(points)]
    lines: list[str] = []
    for start, end in zip(starts, starts[1:]):
        coordinates = ",".join(f"{x:.8f} {y:.8f}" for x, y in points[start:end])
        if coordinates:
            lines.append(f"({coordinates})")
    if len(lines) == 1:
        return f"LINESTRING {lines[0]}"
    return f"MULTILINESTRING ({','.join(lines)})"


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def extract_jeju_nodelink(
    archive_path: str | Path,
    *,
    extract_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Extract Jeju nodes first, then links whose endpoints both resolve in Jeju."""

    archive_path = Path(archive_path)
    extract_dir = Path(extract_dir)
    output_dir = Path(output_dir)
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        node_stem = _select_shapefile_stem(names, "NODE")
        link_stem = _select_shapefile_stem(names, "LINK")
        node_files = _extract_shapefile_group(archive, node_stem, extract_dir / "node")
        link_files = _extract_shapefile_group(archive, link_stem, extract_dir / "link")

    source_crs = CRS.from_wkt(node_files[".prj"].read_text(encoding="utf-8"))
    link_crs = CRS.from_wkt(link_files[".prj"].read_text(encoding="utf-8"))
    if not source_crs.equals(link_crs):
        raise ValueError("Node and link shapefiles use different coordinate systems")
    transformer = Transformer.from_crs(source_crs, CRS.from_epsg(4326), always_xy=True)

    node_rows: list[dict[str, Any]] = []
    jeju_node_ids: set[str] = set()
    source_node_records = 0
    nodes_without_geometry = 0
    node_reader = _reader(node_files)
    for shape_record in node_reader.iterShapeRecords():
        source_node_records += 1
        attributes = _row(shape_record.record)
        node_id = str(_pick(attributes, "node_id") or "").strip()
        if not shape_record.shape.points:
            nodes_without_geometry += 1
            continue
        longitude, latitude = transformer.transform(*shape_record.shape.points[0][:2])
        if parse_point(latitude, longitude) is None:
            continue
        if node_id:
            jeju_node_ids.add(node_id)
        node_rows.append(
            {
                "node_id": node_id,
                "node_name": _pick(attributes, "node_name", "name") or "",
                "node_type": _pick(attributes, "node_type", "node_ty") or "",
                "latitude": round(latitude, 8),
                "longitude": round(longitude, 8),
            }
        )
    node_reader.close()

    link_rows: list[dict[str, Any]] = []
    source_link_records = 0
    links_with_one_jeju_endpoint = 0
    link_reader = _reader(link_files)
    for shape_record in link_reader.iterShapeRecords():
        source_link_records += 1
        attributes = _row(shape_record.record)
        start_node_id = str(
            _pick(attributes, "f_node", "start_node", "start_node_id") or ""
        ).strip()
        end_node_id = str(
            _pick(attributes, "t_node", "end_node", "end_node_id") or ""
        ).strip()
        selected_endpoint_count = sum(
            node_id in jeju_node_ids for node_id in (start_node_id, end_node_id)
        )
        if selected_endpoint_count == 1:
            links_with_one_jeju_endpoint += 1
        if selected_endpoint_count != 2:
            continue
        link_rows.append(
            {
                "link_id": str(_pick(attributes, "link_id") or "").strip(),
                "start_node_id": start_node_id,
                "end_node_id": end_node_id,
                "road_name": _pick(attributes, "road_name") or "",
                "road_rank": _pick(attributes, "road_rank") or "",
                "lane_count": _pick(attributes, "lanes", "lane_count") or "",
                "maximum_speed_limit": _pick(attributes, "max_spd", "maximum_speed")
                or "",
                "road_type": _pick(attributes, "road_type") or "",
                "geometry_wkt": _wkt(shape_record.shape, transformer),
            }
        )
    link_reader.close()

    nodes_path = output_dir / "jeju_nodes.csv"
    links_path = output_dir / "jeju_links.csv"
    _write_csv(
        nodes_path,
        ["node_id", "node_name", "node_type", "latitude", "longitude"],
        node_rows,
    )
    _write_csv(
        links_path,
        [
            "link_id",
            "start_node_id",
            "end_node_id",
            "road_name",
            "road_rank",
            "lane_count",
            "maximum_speed_limit",
            "road_type",
            "geometry_wkt",
        ],
        link_rows,
    )

    return {
        "schema_version": 1,
        "source_archive": archive_path.name,
        "source_archive_sha256": file_sha256(archive_path),
        "source_crs": source_crs.to_string(),
        "target_crs": "EPSG:4326",
        "source_members": {
            "nodes": Path(node_stem).name,
            "links": Path(link_stem).name,
        },
        "output_files": {
            "nodes": str(nodes_path),
            "links": str(links_path),
        },
        "source_node_records": source_node_records,
        "source_link_records": source_link_records,
        "node_rows": len(node_rows),
        "link_rows": len(link_rows),
        "nodes_without_geometry": nodes_without_geometry,
        "links_with_one_jeju_endpoint": links_with_one_jeju_endpoint,
        "selection_rule": "nodes inside broad Jeju bounds; links with both endpoints selected",
    }
