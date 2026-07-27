from ..... import rule
from .....facts import TestCaseGroupFact
from .....models import Count


@rule
def parametrization_candidate_group_count(
    subject: TestCaseGroupFact,
    *,
    minimum_cases: int = 3,
) -> Count:
    """Count safe sibling-test groups that differ only in literal values.

    Definition
    ----------
    Compare direct sibling test functions within the same module or class. Preserve the callable
    kind, fixture parameter names, argument defaults, annotations, decorators, marks, control-flow
    nodes, operators, and call targets. Replace body literals with typed slots, then report a group
    only when at least `minimum_cases` tests have the same remaining syntax and every case has a
    distinct literal vector. The default requires three cases.

    Evidence
    --------
    Each finding spans the candidate group, names every test, and measures both case count and the
    number of literal positions that vary. The rule reports an opportunity and does not rewrite
    test names or invent parameter IDs. The value is the number of qualifying sibling groups rather
    than the number of tests in them.

    Exceptions
    ----------
    Already parametrized tests, tests with docstring scenarios, exception contexts, explicit `try`
    or `raise` statements, external assignment, and common filesystem or monkeypatch side effects
    abstain. Different fixtures, marks, control flow, call targets, or literal types form different
    shapes. Exact duplicate bodies are not parametrization candidates. Ruff PT006, PT007, and PT014
    remain responsible for parametrization syntax and duplicate existing cases.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def test_status_ok(client):
           assert client.get("/ok").status_code == 200

       def test_status_missing(client):
           assert client.get("/missing").status_code == 404

       def test_status_denied(client):
           assert client.get("/denied").status_code == 403

    Good
    ~~~~
    .. code-block:: python

       @pytest.mark.parametrize(
           ("path", "status"),
           [("/ok", 200), ("/missing", 404), ("/denied", 403)],
       )
       def test_status(client, path, status):
           assert client.get(path).status_code == status

    References
    ----------
    Cites "pytest documentation", parametrizing fixtures and test functions
    https://docs.pytest.org/en/stable/how-to/parametrize.html
    Cites "pytest documentation", parametrization examples
    https://docs.pytest.org/en/stable/example/parametrize.html
    Cites Ruff PT014 pytest-duplicate-parametrize-test-cases
    https://docs.astral.sh/ruff/rules/pytest-duplicate-parametrize-test-cases/
    """
    return sum(
        len(group.literal_vectors) >= minimum_cases
        and len({tuple(vector) for vector in group.literal_vectors}) == len(group.literal_vectors)
        for group in subject.groups
    )
