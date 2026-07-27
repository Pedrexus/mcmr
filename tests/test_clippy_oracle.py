from typing import TYPE_CHECKING

import pytest

from mcmr.facts import RustSurfaceFact, SyntaxFact
from tests.oracle import (
    DeclarationReader,
    FindingReader,
    Oracle,
    Relation,
    Site,
    differ,
    needs,
    needs_kernel,
    written,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [needs_kernel, needs("clippy")]

MANIFEST = (
    "[package]\n"
    'name = "elision"\n'
    'version = "0.0.0"\n'
    'edition = "2024"\n\n'
    "[lib]\n"
    'path = "src/lib.rs"\n'
)

# One crate stating every arrangement a lifetime can take, so both readers answer about the same
# source. The lines matter as much as the shapes, since the whole point of the comparison is which
# declaration each reader points at, and every one of them is asserted below by number.
#
#  3 a type naming a lifetime, which has no elision rule at all
#  7 an alias naming one, the same
#  9 a trait naming one, the same
# 13 one input position and no output, which elision produces identically
# 17 two input positions tied together, which elision cannot state
# 21 two input positions with no output, the same
# 25 an output from one input with no receiver, which needs the input arity
# 30 a receiver the return states, which elision produces identically
# 34 an output from a parameter beside a receiver, which elision would take from the receiver
CRATE = """pub struct Node;

pub struct Holder<'a> {
    pub text: &'a str,
}

pub type Pair<'a> = (&'a str, &'a str);

pub trait Named<'a> {
    fn named(&self) -> &'a str;
}

pub fn width<'a>(text: &'a str) -> usize {
    text.len()
}

pub fn tie<'a>(node: &'a Node, found: &mut Vec<&'a Node>) {
    found.push(node);
}

pub fn narrow<'a>(left: &'a str, right: &'a str) -> usize {
    left.len() + right.len()
}

pub fn borrowed<'a>(text: &'a str) -> &'a str {
    text
}

impl Holder<'_> {
    pub fn name<'a>(&'a self) -> &'a str {
        self.text
    }

    pub fn other<'a>(&self, held: &'a str) -> &'a str {
        let _ = self;
        held
    }
}
"""

LIBRARY = "src/lib.rs"


@pytest.fixture(scope="module")
def crate(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write the fixture crate both readers answer about."""
    return written(tmp_path_factory.mktemp("elision"), {"Cargo.toml": MANIFEST, LIBRARY: CRATE})


def test_every_annotation_mcmr_calls_idle_is_one_clippy_calls_idle(crate: Path) -> None:
    """Clippy owns this question for Rust, so a finding it does not share is a finding to justify.

    This is the check that was missing. The rule promised in its own documentation to skip a type
    and a trait, never read the kind, and reported 13 annotations on MCMR's own kernel of which 10
    were structs and aliases with no elision rule to compare against and 3 tied two inputs
    together. Every one of those would appear here as a line Clippy is silent on.
    """
    oracle = Oracle.of("clippy", "needless_lifetimes").report(crate)
    ours = FindingReader(rule_id="RS-LIFE0001", family=RustSurfaceFact, suffixes=(".rs",)).report(
        crate
    )

    assert oracle.states(*(Site.at(LIBRARY, line) for line in (13, 25, 30)))
    assert ours.states(*(Site.at(LIBRARY, line) for line in (13, 30)))
    differ(
        ours,
        Relation.SUBSET,
        oracle,
        because="Clippy reads the type definitions and settles what MCMR declines to guess",
    )


def test_the_one_arrangement_mcmr_declines_is_the_one_it_documents(crate: Path) -> None:
    """The rule states that an output from a sole input with no receiver needs the type arity.

    Clippy reads the type definitions and settles it, MCMR reads one signature and cannot, so the
    difference is written into the comparison rather than tuned away. Naming it keeps the relation
    an equality, so a second arrangement drifting apart fails here instead of hiding inside a
    containment that would still hold.
    """
    oracle = Oracle.of("clippy", "needless_lifetimes").report(crate)
    ours = FindingReader(rule_id="RS-LIFE0001", family=RustSurfaceFact, suffixes=(".rs",)).report(
        crate
    )

    differ(
        ours,
        Relation.EQUALS,
        oracle.minus(Site.at(LIBRARY, 25)),
        because="line 25 turns on how many lifetime positions the input types hold",
    )


def test_statement_without_effect_agrees_with_clippy(tmp_path: Path) -> None:
    """Both readers find the discarded comparison and leave the returned value alone."""
    root = written(
        tmp_path,
        {
            "Cargo.toml": MANIFEST,
            LIBRARY: "pub fn check(value: i32) -> i32 {\n    value == 3;\n    value\n}\n",
        },
    )
    oracle = Oracle.of("clippy", "no_effect").report(root)

    assert oracle.states(Site.at(LIBRARY, 2))
    differ(
        DeclarationReader(
            rule_id="ALL-CONT0002",
            family=SyntaxFact,
            languages=("rust",),
            suffixes=(".rs",),
        ).report(root),
        Relation.EQUALS,
        oracle,
        because="the comparison computes a value that neither statement uses",
    )
