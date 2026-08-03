from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mcmr.rules.general import (
    raise_inside_guarded_region,
    raise_without_cause,
    swallowed_error,
    vanilla_error_type,
)

from .support import query, table, value

if TYPE_CHECKING:
    from mcmr.facts import SyntaxFact
    from mcmr.table import Table


def guarded_corpus(root: Path) -> Table[SyntaxFact]:
    """Build native guards covering protected, handled, nested, and cleanup raises."""
    return table(
        root,
        {
            "guards.py": """def caught(key):
    try:
        record = fetch(key)
        raise StaleRecord(key)
    except StaleRecord:
        return rebuild(key)


def protecting_calls(key):
    try:
        return fetch(key)
    except StaleRecord:
        return rebuild(key)


def under_a_branch(key):
    try:
        record = fetch(key)
        if record.expired:
            raise StaleRecord(key)
    except StaleRecord:
        return rebuild(key)


def extracted(key):
    def fresh():
        raise StaleRecord(key)
    try:
        return fresh()
    except StaleRecord:
        return rebuild(key)


def cleanup_only(key):
    try:
        raise StaleRecord(key)
    finally:
        close(key)


def another_type(kind):
    try:
        raise QuotaExceeded(kind)
    except DatabaseError as error:
        retry(error)


def bare_reraise():
    try:
        raise
    except:
        recover()


def handler_raise():
    try:
        read()
    except ValueError:
        raise ValueError("invalid")


def nested_cleanup(key):
    try:
        raise StaleRecord(key)
        try:
            fetch(key)
        except StaleRecord:
            recover(key)
    finally:
        close(key)


def later_raise(key):
    try:
        def fresh():
            raise StaleRecord(key)
        raise StaleRecord(key)
    except StaleRecord:
        rebuild(key)


def bare(key):
    try:
        raise StaleRecord(key)
    except:
        return None


def broad(key):
    try:
        raise StaleRecord(key)
    except Exception:
        return None
""",
            "guards.cpp": """void typed() {
    try {
        throw StaleRecord();
    } catch (const StaleRecord& error) {
        rebuild();
    }
}
""",
            "guards.ts": """function untyped() {
  try {
    throw new StaleRecord();
  } catch (error) {
    rebuild();
  }
}
""",
        },
    )


def test_a_guard_that_catches_what_its_own_body_threw(tmp_path: Path) -> None:
    """A matching handler catches a protected raise but not one hidden in a nested callable."""
    subject = guarded_corpus(tmp_path)
    result = query(raise_inside_guarded_region, subject)

    assert value(result, subject, "caught") == 1
    assert value(result, subject, "protecting_calls") == 0
    assert value(result, subject, "under_a_branch") == 1
    assert value(result, subject, "extracted") == 0


def test_a_guard_no_clause_of_which_would_catch_the_raise_is_left_alone(tmp_path: Path) -> None:
    """Cleanup and differently typed handlers catch none of their protected raises."""
    subject = guarded_corpus(tmp_path)
    result = query(raise_inside_guarded_region, subject)

    assert value(result, subject, "cleanup_only") == 0
    assert value(result, subject, "another_type") == 0


@pytest.mark.parametrize(
    ("qualname", "expected"),
    (
        pytest.param("bare_reraise", 0, id="bare-reraise"),
        pytest.param("handler_raise", 0, id="handler-raise"),
        pytest.param("cleanup_only", 0, id="cleanup-only"),
        pytest.param("nested_cleanup", 0, id="nested-cleanup"),
        pytest.param("later_raise", 1, id="later-raise"),
    ),
)
def test_guarded_region_boundaries_keep_only_the_raises_the_guard_catches(
    tmp_path: Path, qualname: str, expected: int
) -> None:
    """Reraises, handlers, cleanup, nested guards, and later statements keep their boundaries."""
    subject = guarded_corpus(tmp_path)
    result = query(raise_inside_guarded_region, subject)

    assert value(result, subject, qualname) == expected


def test_a_clause_that_names_no_type_or_a_base_type_catches_whatever_the_body_threw(
    tmp_path: Path,
) -> None:
    """Bare, broad, typed, and binding-only handlers catch protected raises."""
    subject = guarded_corpus(tmp_path)
    default = query(raise_inside_guarded_region, subject)
    no_catch_all = query(raise_inside_guarded_region, subject, catch_all=[])

    assert value(default, subject, "bare") == 1
    assert value(default, subject, "broad") == 1
    assert value(no_catch_all, subject, "broad") == 0
    assert value(default, subject, "typed") == 1
    assert value(default, subject, "untyped") == 1


def test_a_quiet_declaration_is_never_judged(tmp_path: Path) -> None:
    """A native declaration without error syntax answers zero for every error query."""
    subject = table(
        tmp_path,
        {"quiet.py": "def quiet():\n    return 1\n"},
    )

    assert value(query(swallowed_error, subject), subject, "quiet") == 0
    assert value(query(raise_without_cause, subject), subject, "quiet") == 0
    assert value(query(vanilla_error_type, subject), subject, "quiet") == 0
    assert value(query(raise_inside_guarded_region, subject), subject, "quiet") == 0


def test_a_type_reaches_its_code_through_the_callables_it_owns(tmp_path: Path) -> None:
    """The type row stays quiet while its callable owns each error finding."""
    subject = table(
        tmp_path,
        {
            "owner.py": """class Owner:
    def run(self):
        try:
            raise Exception()
        except OSError:
            pass
"""
        },
    )

    assert value(query(swallowed_error, subject), subject, "Owner") == 0
    assert value(query(raise_without_cause, subject), subject, "Owner") == 0
    assert value(query(vanilla_error_type, subject), subject, "Owner") == 0
    assert value(query(raise_inside_guarded_region, subject), subject, "Owner") == 0
