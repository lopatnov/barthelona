import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from barthelona.llm import zetaris_publish as publish
from barthelona.llm.zetaris import ZetarisConfig, ZetarisError

CONFIG = ZetarisConfig("http://zetaris.test/api/v1.0", "1", "k")


def _db(path: Path) -> Path:
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE runs (id INTEGER, label TEXT)")
    db.execute("INSERT INTO runs VALUES (1, 'a,b'), (2, 'say \"hi\"')")
    db.commit()
    db.close()
    return path


def test_export_writes_header_and_quoted_rows(tmp_path: Path) -> None:
    source = publish.Source(_db(tmp_path / "r.sqlite"), "runs", "runs")
    target = publish.export_csv(source, tmp_path / "out")
    assert target.read_text(encoding="utf-8") == 'id,label\n1,"a,b"\n2,"say ""hi"""\n'


def test_export_of_a_missing_table_is_a_zetaris_error(tmp_path: Path) -> None:
    source = publish.Source(_db(tmp_path / "r.sqlite"), "nope", "nope")
    with pytest.raises(ZetarisError, match="cannot export"):
        publish.export_csv(source, tmp_path / "out")


def test_register_missing_creates_only_what_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sql = json.loads(request.content)["sql"]
        sent.append(sql)
        if sql == "SHOW LIGHTNING DATABASES":
            return httpx.Response(200, json={"data": [[publish.DATABASE, "d", 1]]})
        if sql.startswith("SHOW LIGHTNING TABLES"):
            return httpx.Response(200, json={"data": [["runs", None, "p"]]})
        return httpx.Response(200, json={"data": []})

    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler)))
    assert publish.register_missing(CONFIG, ["runs", "memories"]) == ["memories"]
    assert sum(sql.startswith("CREATE LIGHTNING FILESTORE TABLE memories") for sql in sent) == 1
    assert not any(sql.startswith("CREATE LIGHTNING DATABASE") for sql in sent)
