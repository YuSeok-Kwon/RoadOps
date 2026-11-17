from roadops.accident_hotspots import normalize_official_csv


def _csv_bytes():
    text = "\n".join(
        [
            '"\uc0ac\uace0\ub2e4\ubc1c\uc9c0fid","\uc0ac\uace0\ub2e4\ubc1c\uc9c0id","\ubc95\uc815\ub3d9\ucf54\ub4dc","\uc9c0\uc810\ucf54\ub4dc","\uc2dc\ub3c4\uc2dc\uad70\uad6c\uba85","\uc9c0\uc810\uba85","\uc0ac\uace0\uac74\uc218","\uc0ac\uc0c1\uc790\uc218","\uc0ac\ub9dd\uc790\uc218","\uc911\uc0c1\uc790\uc218","\uacbd\uc0c1\uc790\uc218","\ubd80\uc0c1\uc2e0\uace0\uc790\uc218","\uacbd\ub3c4","\uc704\ub3c4","\ub2e4\ubc1c\uc9c0\uc5ed\ud3f4\ub9ac\uace4"',
            '"1","2025134","5011010100","50110001","\uc81c\uc8fc \uc81c\uc8fc\uc2dc1","\uc81c\uc8fc\uc2dc \uc774\ub3c4\uc774\ub3d9(\uad11\uc591\uc0ac\uac70\ub9ac \ubd80\uadfc)","30","40","0","4","36","0","126.52","33.50","{\"\"type\"\":\"\"Polygon\"\",\"\"coordinates\"\":[[[126.51,33.49],[126.53,33.49],[126.51,33.49]]]}"',
            '"2","2026134","5011010100","50110001","\uc81c\uc8fc \uc81c\uc8fc\uc2dc1","\uc81c\uc8fc\uc2dc \uc774\ub3c4\uc774\ub3d9(\uad11\uc591\uc0ac\uac70\ub9ac \ubd80\uadfc)","42","55","1","8","46","0","126.53","33.50","{\"\"type\"\":\"\"Polygon\"\",\"\"coordinates\"\":[[[126.52,33.49],[126.54,33.49],[126.52,33.49]]]}"',
            '"3","2026134","1111010100","11110001","\uc11c\uc6b8 \uc885\ub85c\uad6c1","\uc11c\uc6b8 \uc885\ub85c\uad6c","99","100","0","0","100","0","127.0","37.5","{\"\"type\"\":\"\"Polygon\"\",\"\"coordinates\"\":[]}"',
        ]
    )
    return text.encode("cp949")


def test_normalize_official_csv_keeps_latest_jeju_publication():
    rows, report = normalize_official_csv(_csv_bytes())

    assert len(rows) == 1
    assert rows[0]["analysis_year"] == 2025
    assert rows[0]["accident_count"] == 42
    assert rows[0]["source_mode"] == "official_csv"
    assert report["latest_publication_year"] == 2026
    assert report["jeju_row_count"] == 2
