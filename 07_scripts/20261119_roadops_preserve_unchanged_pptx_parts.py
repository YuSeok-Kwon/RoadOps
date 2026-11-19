"""Transfer the Artifact Tool photo edit while preserving all other PPTX parts."""
import json
import posixpath
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = {
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}


def target_part(owner, target):
    return target.lstrip('/') if target.startswith('/') else posixpath.normpath(
        posixpath.join(posixpath.dirname(owner), target))


def parts(archive):
    owner = 'ppt/slides/slide2.xml'
    slide = ET.fromstring(archive.read(owner))
    matches = []
    for pic in slide.findall('.//p:pic', NS):
        off = pic.find('p:spPr/a:xfrm/a:off', NS)
        ext = pic.find('p:spPr/a:xfrm/a:ext', NS)
        if off is not None and ext is not None and (off.get('x'), off.get('y'), ext.get('cx'), ext.get('cy')) == ('609600', '2047875', '5381625', '3943350'):
            matches.append(pic.find('p:blipFill/a:blip', NS).get('{'+NS['r']+'}embed'))
    assert len(matches) == 1, 'Expected one photograph at the reviewed position'
    rels = ET.fromstring(archive.read('ppt/slides/_rels/slide2.xml.rels'))
    photo = next(target_part(owner, r.get('Target')) for r in rels if r.get('Id') == matches[0])
    notes = next(target_part(owner, r.get('Target')) for r in rels if r.get('Type').endswith('/notesSlide'))
    return photo, notes


def main():
    source, edited, output = map(Path, sys.argv[1:])
    assert output.resolve() not in (source.resolve(), edited.resolve())
    with ZipFile(source) as original, ZipFile(edited) as changed:
        photo, notes = parts(original)
        edited_photo, edited_notes = parts(changed)
        # Replacing a shared media part would affect other slides. Refuse that.
        for name in original.namelist():
            if name.startswith('ppt/slides/_rels/slide') and name.endswith('.rels') and name != 'ppt/slides/_rels/slide2.xml.rels':
                owner = name.replace('/_rels/', '/').removesuffix('.rels')
                for rel in ET.fromstring(original.read(name)):
                    assert target_part(owner, rel.get('Target')) != photo, 'Photo is shared by another slide'
        replacements = {photo: changed.read(edited_photo), notes: changed.read(edited_notes)}
        with ZipFile(output, 'w') as result:
            for entry in original.infolist():
                result.writestr(entry, replacements.get(entry.filename, original.read(entry.filename)))
    with ZipFile(source) as original, ZipFile(output) as result:
        assert original.namelist() == result.namelist()
        different = [name for name in original.namelist() if original.read(name) != result.read(name)]
        assert set(different) == set(replacements), different
    print(json.dumps({'changed_parts': different, 'all_other_parts_identical': True, 'chart_workbooks_preserved': True}))


if __name__ == '__main__':
    main()
