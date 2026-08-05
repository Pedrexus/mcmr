from pathlib import Path

import pytest

from mcmr.rules.general import abstraction_nothing_depends_on, dependency_on_a_less_stable_module

from ...support import needs_kernel
from .support import built, coupling, fact, fact_table, named, query, value, values


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """Write one package whose coupling and abstractness are small enough to work out by hand.

    `core` is imported by both other modules and imports neither, `reader` imports `core` and is
    imported by `writer`, and `writer` imports both and is imported by nothing. `core` declares
    four types of which one is a contract, `reader` declares two concrete ones, and `writer`
    declares none.
    """
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "core.py").write_text(
        """from abc import ABC, abstractmethod


class Codec(ABC):
    @abstractmethod
    def encode(self) -> str: ...


class Frame:
    width = 1


class Packet:
    size = 2


class Header:
    kind = 3
"""
    )
    (package / "reader.py").write_text(
        """from pkg.core import Frame


class Reader:
    frame = Frame


class Buffer:
    depth = 4
"""
    )
    (package / "writer.py").write_text(
        """from pkg.core import Packet
from pkg.reader import Reader


def write(reader: Reader) -> Packet:
    return Packet()
"""
    )
    return tmp_path


@needs_kernel
def test_the_kernel_states_the_counts_this_fixture_was_written_to_produce(
    repository: Path,
) -> None:
    """Every number below is read off the fixture rather than off the implementation."""
    facts = built(str(repository))
    core = named(facts, "pkg.core")
    reader = named(facts, "pkg.reader")
    writer = named(facts, "pkg.writer")

    assert [
        (
            fact.afferent_count,
            fact.efferent_count,
            fact.declaration_count,
            fact.abstract_declaration_count,
        )
        for fact in (core, reader, writer)
    ] == [(2, 0, 4, 1), (1, 1, 2, 0), (0, 2, 0, 0)]
    assert [item.module for item in writer.dependencies] == ["pkg.core", "pkg.reader"]
    assert writer.dependencies[0].afferent_count == 2


@needs_kernel
def test_the_metrics_over_that_fixture_are_the_ones_martin_defines(repository: Path) -> None:
    """`I`, `A`, and `D` for three modules, each worked out by hand from the counts above."""
    facts = built(str(repository))
    core = named(facts, "pkg.core")
    reader = named(facts, "pkg.reader")
    writer = named(facts, "pkg.writer")

    assert (core.instability, core.abstractness, core.distance) == (0.0, 0.25, 0.75)
    assert (reader.instability, reader.abstractness, reader.distance) == (0.5, 0.0, 0.5)
    assert (writer.instability, writer.abstractness, writer.distance) == (1.0, 0.0, 0.0)


@needs_kernel
def test_the_rules_read_that_fixture_the_way_the_metrics_say_they_should(
    repository: Path,
) -> None:
    """Every arrow points toward stability here, so the layering rule reports nothing at all."""
    facts = built(str(repository))
    table = fact_table(facts[0], *facts[1:])

    assert values(query(table, dependency_on_a_less_stable_module)) == [0]
    assert not any(values(query(table, abstraction_nothing_depends_on)))


@pytest.fixture
def inverted(tmp_path: Path) -> Path:
    """Write the same three modules with one arrow turned around, which is the violation.

    `core` now imports `writer`, and `writer` is imported by nothing else and imports two modules,
    so the settled module has taken a dependency on the volatile one.
    """
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "core.py").write_text("from pkg.writer import write\n\n\nvalue = write\n")
    (package / "reader.py").write_text("from pkg.core import value\n\n\nread = value\n")
    (package / "writer.py").write_text(
        "from pkg.helper import helper\n\n\ndef write() -> int:\n    return helper()\n"
    )
    (package / "helper.py").write_text("def helper() -> int:\n    return 1\n")
    return tmp_path


@needs_kernel
def test_an_arrow_within_one_package_is_not_a_component_violation(
    inverted: Path,
) -> None:
    """A file edge inside one package never crosses the component boundary."""
    facts = built(str(inverted))
    core = named(facts, "pkg.core")
    writer = named(facts, "pkg.writer")

    assert (core.afferent_count, core.efferent_count) == (1, 1)
    assert (writer.afferent_count, writer.efferent_count) == (1, 1)
    assert core.instability == 0.5
    assert writer.instability == 0.5
    table = fact_table(core)
    assert value(table, dependency_on_a_less_stable_module) == 0
    assert value(table, dependency_on_a_less_stable_module, tolerance=-0.1) == 0


def test_a_package_initializer_declares_ownership_without_creating_a_component_arrow() -> None:
    """A public facade may reexport a nested implementation without depending on its volatility."""
    initializer = fact(
        module="pkg.api",
        path="pkg/api/__init__.py",
        dependencies=[coupling("pkg.api.models.item", afferent=0, efferent=0)],
    )
    model = fact(module="pkg.api.models.item", path="pkg/api/models/item.py")

    assert not any(
        values(
            query(
                fact_table(initializer, model),
                dependency_on_a_less_stable_module,
                tolerance=-0.1,
            )
        )
    )

    rust_facade = fact(
        module="engine.api",
        path="engine/src/api/mod.rs",
        dependencies=[coupling("engine.api.models.item", afferent=0, efferent=0)],
    )
    rust_model = fact(module="engine.api.models.item", path="engine/src/api/models/item.rs")
    assert not any(
        values(
            query(
                fact_table(rust_facade, rust_model),
                dependency_on_a_less_stable_module,
                tolerance=-0.1,
            )
        )
    )
