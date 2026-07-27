from ..... import rule
from .....facts import TestFunctionFact
from .....models import Count


@rule
def legacy_tmpdir_fixture_count(
    subject: TestFunctionFact,
) -> Count:
    """Count uses of pytest's legacy `tmpdir` fixtures.

    Definition
    ----------
    Inspect test modules and `conftest.py` files for injected parameters named `tmpdir` or
    `tmpdir_factory`. Also count those names when supplied to `request.getfixturevalue` or
    `pytest.mark.usefixtures`. The modern `tmp_path` and `tmp_path_factory` fixtures return
    standard-library `pathlib.Path` values and are the preferred default.

    Evidence
    --------
    Each finding locates one fixture parameter or one dynamic fixture request and identifies the
    legacy fixture name. Ordinary local variables called `tmpdir` are not fixture evidence. The
    value is the number of legacy fixture uses across every collected test.

    Exceptions
    ----------
    A test that depends on `py.path.local` behavior can exclude its path or retain the finding with
    an explicit project policy. The rule does not auto-fix because `py.path.local` methods and
    `pathlib.Path` methods are not mechanically equivalent. Ruff has no pytest-style rule that
    migrates these fixtures.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def test_report(tmpdir):
           report = tmpdir.join("report.json")
           assert report.ext == ".json"

    Good
    ~~~~
    .. code-block:: python

       def test_report(tmp_path):
           report = tmp_path / "report.json"
           assert report.suffix == ".json"

    References
    ----------
    Cites "pytest documentation", temporary directory
    https://docs.pytest.org/en/stable/how-to/tmp_path.html#the-tmpdir-and-tmpdir-factory-fixtures
    Cites "The Python Standard Library", pathlib
    https://docs.python.org/3/library/pathlib.html
    """
    legacy = {"tmpdir", "tmpdir_factory"}
    return sum(
        len(legacy.intersection({*test.fixture_names, *test.requested_fixture_names}))
        for test in subject.tests
        if test.is_collected
    )
