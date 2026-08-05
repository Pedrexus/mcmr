import json
from pathlib import Path

import anyio
import pytest
from mcmr_datahub.provider import DataHubProvider

from mcmr.commands.quality import writeback
from mcmr.plugins import PublicationContext

from ...support import needs_kernel, project_root, written

_EXAMPLE = project_root() / "examples" / "datahub"

_PROJECT = """[tool.mcmr.execution]
external = true

[tool.mcmr.providers.datahub]
recorded = "recordings"
report_url = "https://example.invalid/run"
page_size = 10
max_assets = 10
"""

_GOVERNED = {
    "urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,ecommerce.marts.clean,PROD)",
    "properties": {"description": "Everything this asset needs.", "lastModified": {"time": 0}},
    "deprecation": None,
    "ownership": {"owners": [{"owner": {"urn": "urn:li:corpGroup:data", "name": "data"}}]},
    "domain": {"domain": {"urn": "urn:li:domain:sales", "properties": {"name": "Sales"}}},
    "schemaMetadata": {
        "fields": [
            {
                "fieldPath": "id",
                "type": "NUMBER",
                "description": "Row identifier.",
                "globalTags": None,
                "glossaryTerms": None,
            }
        ]
    },
}


def clean(root: Path) -> Path:
    """Write one repository whose recorded catalog leaves nothing for a rule to report."""
    recordings = root / "recordings"
    recordings.mkdir(parents=True)
    (recordings / "MCMRDataAssets.json").write_text(
        json.dumps(
            [
                {
                    "variables": {"query": "*", "count": 10, "start": 0},
                    "response": {
                        "data": {
                            "searchAcrossEntities": {
                                "total": 1,
                                "searchResults": [{"entity": _GOVERNED}],
                            }
                        }
                    },
                }
            ]
        )
    )
    for operation, answer in (
        ("MCMRFieldLineage", {"dataset": {"urn": _GOVERNED["urn"], "fineGrainedLineages": []}}),
        ("MCMRDataLineage", {"searchAcrossLineage": {"total": 0, "searchResults": []}}),
    ):
        variables = {"urn": _GOVERNED["urn"]}
        if operation == "MCMRDataLineage":
            variables = variables | {"count": 10, "start": 0}
        (recordings / f"{operation}.json").write_text(
            json.dumps([{"variables": variables, "response": {"data": answer}}])
        )
    return written(
        root,
        {
            "pyproject.toml": _PROJECT,
            "rollup.py": '"""A rollup naming nothing the catalog governs."""\n\nTOTAL = 1\n',
        },
    )


@needs_kernel
def test_a_run_that_names_no_governed_asset_writes_nothing_back(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Writeback is evidence-driven, so a clean catalog produces no link and no request."""
    writeback(clean(tmp_path), select="data_assets")

    assert "nothing was written back" in capsys.readouterr().out


def test_writeback_refuses_to_publish_without_somewhere_to_point(tmp_path: Path) -> None:
    """A link with no destination states nothing, so the provider fails before it connects."""
    context = PublicationContext(
        repository=tmp_path,
        settings={"server": "https://catalog.example"},
        subjects=["urn:li:dataset:(snowflake,orders,PROD)"],
    )

    with pytest.raises(ValueError, match="requires `report_url`"):
        anyio.run(DataHubProvider().publish, context)


@needs_kernel
def test_the_recorded_run_links_every_governed_asset_it_named(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every asset a finding named now points at the analysis, and none of them was overwritten."""
    root = tmp_path / "example"
    root.mkdir()
    for source in _EXAMPLE.rglob("*"):
        target = root / source.relative_to(_EXAMPLE)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_file():
            target.write_text(source.read_text())

    writeback(root, select="data_assets")

    output = capsys.readouterr().out
    assert (
        output.count("wrote back"),
        "3 of 3 governed assets carry this run." in output.replace("\n", " ").replace("  ", " "),
    ) == (3, True)
