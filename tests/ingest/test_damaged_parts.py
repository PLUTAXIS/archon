"""A damaged workbook part is skipped with a logged warning, never silently."""

import logging
import zipfile

from archon.ingest.xlsx import _defined_names, _sheet_visibility


def test_missing_or_broken_parts_are_logged(tmp_path, caplog):
    path = tmp_path / "broken.xlsx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", "<workbook><not closed")
    with caplog.at_level(logging.WARNING, logger="archon.ingest.xlsx"):
        assert _sheet_visibility(path) == {}
        assert _defined_names(path) == []
    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("skipped unreadable sheet visibility") for m in messages)
    assert any(m.startswith("skipped unreadable defined names") for m in messages)
