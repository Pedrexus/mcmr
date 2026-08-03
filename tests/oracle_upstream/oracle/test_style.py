from pathlib import Path

from mcmr.facts import (
    AttributeAccessFact,
    CommentFact,
    ModuleFact,
)

from ...oracle import (
    DeclarationReader,
    Oracle,
    RecordReader,
    Relation,
    Site,
    differ,
    written,
)


def test_protected_access_agrees_with_pylint(tmp_path: Path) -> None:
    """The other exact claim, on a fixture stating every way a reach can stay inside its owner.

    Comparing the files both readers named was no comparison at all, since both sides reduce to one
    filename on a one-file tree. The accesses are compared instead, so every way an owner reaches
    its own member has to be allowed by both, and only the two reaches from outside are reported.
    """
    root = written(
        tmp_path,
        {
            "generated.py": """class Engine:
    def __init__(self):
        self._limit = 3

    def run(self):
        return self._limit

    @classmethod
    def build(cls):
        return cls._limit

    def owner(self):
        return Engine._limit

    def nested(self):
        def inner():
            return self._limit

        return inner()

    def protocol(self):
        return self.__class__.__name__


class Faster(Engine):
    def run(self):
        return super()._limit


def outside(engine):
    engine._limit = 4
    return engine._limit
"""
        },
    )
    oracle = Oracle.of("pylint", "protected-access").report(root)

    assert oracle.states(Site.at("generated.py", 31), Site.at("generated.py", 32))
    differ(
        RecordReader(rule_id="ALL-ENCA0001", family=AttributeAccessFact, field="accesses").report(
            root
        ),
        Relation.EQUALS,
        oracle,
        because="every way an owner reaches its own member is owner access to both readers",
    )


def test_protected_access_is_stricter_than_pylint_about_a_base_a_subclass_names(
    tmp_path: Path,
) -> None:
    """Pylint lets a subclass reach a base member by the base's own name, and MCMR does not.

    Owner access under the strict default is `self`, `cls`, `super()`, and the innermost lexical
    class by name. Pylint additionally allows any name a class lists as a base, so a subclass
    reaching `Engine._limit` is silent there and reported here. Naming that one reach keeps the
    relation an equality, where a containment would still have held had MCMR lost the reach from
    the unrelated class as well.
    """
    root = written(
        tmp_path,
        {
            "generated.py": """class Engine:
    def __init__(self):
        self._limit = 3


class Faster(Engine):
    def reach(self):
        return Engine._limit


class Stranger:
    def reach(self):
        return Engine._limit
"""
        },
    )
    oracle = Oracle.of("pylint", "protected-access").report(root)

    assert oracle.states(Site.at("generated.py", 13))
    differ(
        RecordReader(rule_id="ALL-ENCA0001", family=AttributeAccessFact, field="accesses").report(
            root
        ),
        Relation.EQUALS,
        oracle.plus(Site.at("generated.py", 8)),
        because="Pylint allows a reach through any name a class lists as a base and MCMR does not",
    )


def test_unresolved_work_marker_agrees_with_pylint(tmp_path: Path) -> None:
    """Pylint's default notes are `FIXME`, `XXX`, and `TODO`, so the rule is asked for those.

    MCMR carries `HACK` too, which Ruff reports as `FIX004` and Pylint does not report at all, so
    the setting is narrowed here rather than the fixture being written around the difference.
    """
    root = written(
        tmp_path,
        {
            "generated.py": """# TODO: handle the empty case
# rewrite the todo list before shipping


def load(path):
    # FIXME: this loses the encoding
    text = read(path)

    return text  # XXX later
"""
        },
    )
    oracle = Oracle.of("pylint", "fixme").report(root)
    ours = RecordReader(
        rule_id="ALL-COMM0003",
        family=CommentFact,
        field="groups",
        settings={"markers": ("todo", "fixme", "xxx")},
    ).report(root)

    assert oracle.states(
        Site.at("generated.py", 1), Site.at("generated.py", 6), Site.at("generated.py", 9)
    )
    differ(
        ours,
        Relation.EQUALS,
        oracle,
        because="asked for Pylint's own three notes, the two readers open on the same comments",
    )


def test_the_work_marker_reader_is_wider_than_the_one_pylint_has(tmp_path: Path) -> None:
    """The reader is neutral and every frontend that fills the family widens it for free.

    `unresolved_work_marker` opens on `#`, `//`, and `/*` alike, so the day a frontend fills
    `CommentFact` this rule answers for that language with no change. Pylint can only ever answer
    for Python, so the Rust marker is named in the comparison rather than the relation being
    loosened to a containment any silent reader would satisfy.

    The comments are compared rather than the facts holding them. One `CommentFact` covers a whole
    file, so every fact starts on line one and a containment over fact spans was true whatever
    either reader answered.
    """
    root = written(
        tmp_path,
        {
            "generated.py": "def run():\n    return 1\n\n\n# TODO: python\n",
            "generated.rs": "fn run() {}\n\n// FIXME: rust\n",
        },
    )
    oracle = Oracle.of("pylint", "fixme").report(root)
    ours = RecordReader(rule_id="ALL-COMM0003", family=CommentFact, field="groups").report(root)

    assert oracle.states(Site.at("generated.py", 5))
    differ(
        ours,
        Relation.EQUALS,
        oracle.plus(Site.at("generated.rs", 3)),
        because="the neutral reader answers for Rust as well, where Pylint can only read Python",
    )


def test_non_ascii_source_path_agrees_with_pylint(tmp_path: Path) -> None:
    """On a flat tree the two answer identically, since only the last component differs.

    Both readers judge one file at a time and the paths compared are the ones relative to the tree,
    so the quiet file makes this a real check rather than an arithmetic one. Pylint names the first
    line of the module and MCMR answers for the whole of it, which is what the fold is for.
    """
    root = written(
        tmp_path,
        {
            "café.py": "def run():\n    return 1\n",
            "plain.py": "def run():\n    return 2\n",
        },
    )
    oracle = Oracle.of("pylint", "non-ascii-file-name").report(root)

    assert oracle.states(Site.at("café.py", 1))
    differ(
        DeclarationReader(rule_id="ALL-MODU0004", family=ModuleFact).report(root),
        Relation.EQUALS,
        oracle,
        because="a name a build system cannot reproduce is the same defect to both readers",
    )


def test_non_ascii_source_path_judges_the_directories_pylint_skips(tmp_path: Path) -> None:
    """Pylint judges the module name alone, and a build system reproduces the whole path.

    Every component has to survive an archive, a command line, and another platform's shell, so
    MCMR is deliberately the wider reader and the one module Pylint stays quiet about is named in
    the comparison rather than left to a containment.
    """
    root = written(
        tmp_path,
        {
            "naïve/reader.py": "def run():\n    return 1\n",
            "plain.py": "def run():\n    return 2\n",
        },
    )
    oracle = Oracle.of("pylint", "non-ascii-file-name").report(root)

    assert oracle.states()
    differ(
        DeclarationReader(rule_id="ALL-MODU0004", family=ModuleFact).report(root),
        Relation.EQUALS,
        oracle.plus(Site.at("naïve/reader.py", 1)),
        because="Pylint reads the module name where MCMR reads every component of the path",
    )
