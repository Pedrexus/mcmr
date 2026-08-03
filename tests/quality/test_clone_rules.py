import re
import subprocess
from pathlib import Path
from typing import cast

import pytest

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import CloneFragment, CloneGroupFact, Fact, SourceSpan
from mcmr.kernel import locate
from mcmr.query import RuleQuery, scalar_frame_value
from mcmr.rules.general import duplicated_repository_share, pasted_block_copy_count
from mcmr.table import AnalysisSession, GenericRelation, Table, fact_table

_ROOT = Path(__file__).parents[2]

# One module whose only interesting property is the block another module also states. The lines
# around it differ on purpose, so neither reader can grow the match past what was really pasted.
_LEADING = 'CONFIG = {"retries": 2}\n\n\n'
_FOLLOWING = "def describe(name):\n    return name.upper()\n\n\n"
_BLOCK = """def {name}({rows}, {limit}):
    {total} = 0
    for {row} in {rows}:
        if {row}.value > {limit}:
            {total} = {total} + {row}.value * 2
        else:
            {total} = {total} - 1
    if {total} < 0:
        return 0
    return {total}
"""
_ORIGINAL = _BLOCK.format(name="collect", rows="rows", limit="limit", total="total", row="row")
_RENAMED = _BLOCK.format(name="gather", rows="items", limit="floor", total="carried", row="item")


def fragment(path: str, *, start: int, end: int) -> CloneFragment:
    """Build one copy of a repeated fragment at a stated place."""
    return CloneFragment(path=path, start_line=start, end_line=end)


def group(*fragments: CloneFragment, tokens: int = 90, repository: int = 400) -> CloneGroupFact:
    """Build one clone group the way the kernel states it."""
    return CloneGroupFact(
        key="clone:a.py:1:90",
        span=SourceSpan(path=fragments[0].path if fragments else ""),
        language="python",
        fragments=list(fragments),
        token_length=tokens,
        repository_line_count=repository,
    )


def paste(root: Path, copied: str) -> None:
    """Write two modules that share one block and differ everywhere else."""
    (root / "module_a.py").write_text(_LEADING + _ORIGINAL)
    (root / "module_b.py").write_text(_FOLLOWING + copied)


def query(
    rule: RuleContract,
    table: Table[Fact],
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one clone rule once over a typed table."""
    result = rule.invoke_table(table, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic clone rule returned a model query")
    return result


def retained(subject: CloneGroupFact) -> Table[Fact]:
    """Normalize one stated clone group through the in-memory table boundary."""
    return fact_table(CloneGroupFact, [subject])


def value(
    rule: RuleContract,
    table: Table[Fact],
    **settings: RuleSetting,
) -> RuleValue:
    """Return the only clone scalar from one table-rule invocation."""
    return scalar_frame_value(query(rule, table, **settings).values.collect())


def symilar_blocks(root: Path) -> tuple[list[set[tuple[str, int, int]]], float]:
    """Return the blocks Symilar reports over one tree, and the share it says they occupy.

    Symilar prints a half-open slice into the real lines of each file, so `[3:13]` names the ten
    lines a reader would call four through thirteen. Both numbers are turned back into the lines a
    person would point at, which is the only form the two tools can be compared in.
    """
    completed = subprocess.run(
        [
            "python",
            "-m",
            "pylint.checkers.symilar",
            "--duplicates=4",
            *sorted(str(path) for path in root.glob("*.py")),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    blocks: list[set[tuple[str, int, int]]] = []
    current: set[tuple[str, int, int]] = set()
    share = 0.0
    for line in completed.stdout.splitlines():
        if re.fullmatch(r"\d+ similar lines in \d+ files", line):
            current = set()
            blocks.append(set())
        elif found := re.fullmatch(r"==(.+):\[(\d+):(\d+)\]", line):
            current.add((Path(found[1]).name, int(found[2]) + 1, int(found[3])))
            blocks[-1] = set(current)
        elif found := re.fullmatch(r"TOTAL lines=\d+ duplicates=\d+ percent=([\d.]+)", line):
            share = float(found[1])
    return blocks, share


def mcmr_blocks(root: Path) -> tuple[list[set[tuple[str, int, int]]], Table[Fact]]:
    """Return the blocks MCMR reports over the same tree, in the same form."""
    table = cast(
        "Table[Fact]",
        AnalysisSession(
            root,
            suffixes=[".py"],
            typed_families=[CloneGroupFact.__name__],
        ).table(CloneGroupFact),
    )
    fragments = table.frame(GenericRelation.RECORDS).filter(
        table.frame(GenericRelation.RECORDS)["relation"] == "fragments"
    )
    blocks = [
        {
            (
                Path(row["path"]).name,
                row["start_line"],
                row["end_line"],
            )
            for row in fragments.filter(fragments["fact_id"] == fact_id).iter_rows(named=True)
            if isinstance(row["path"], str)
            and isinstance(row["start_line"], int)
            and isinstance(row["end_line"], int)
        }
        for fact_id in fragments.get_column("fact_id").unique(maintain_order=True)
    ]
    return blocks, table


def test_a_block_is_only_a_paste_once_it_is_long_enough_to_be_one() -> None:
    """Normalization discards every name, so a short run of shape is not evidence of a copy."""
    copied = group(fragment("a.py", start=4, end=13), fragment("b.py", start=5, end=14))

    table = retained(copied)
    assert value(pasted_block_copy_count, table) == 1
    assert value(pasted_block_copy_count, table, minimum_token_length=200) == 0
    assert value(pasted_block_copy_count, table, minimum_line_count=40) == 0


def test_a_block_pasted_twice_is_worth_two_deletions() -> None:
    """One of the copies is the one worth keeping, so the value is what a merge would remove."""
    spread = group(
        fragment("a.py", start=1, end=12),
        fragment("b.py", start=1, end=12),
        fragment("c.py", start=1, end=12),
    )

    table = retained(spread)
    assert value(pasted_block_copy_count, table) == 2
    assert value(duplicated_repository_share, table) == pytest.approx(6.0)


@pytest.mark.skipif(
    not locate(_ROOT).exists(),
    reason="the differential oracle needs the kernel binary this checkout builds",
)
class TestAgainstSymilar:
    """Check the clone detector against Pylint's own, which ships as `symilar`.

    The two tools do not ask the same question and pretending they do would be the dishonest way
    to pass. Symilar compares stripped lines of text, so a block only matches where the copy kept
    every name and every literal. MCMR compares normalized tokens, so a copy still matches after
    its locals were renamed and its formatting was redone. That makes MCMR strictly the wider
    reader, and the relationship worth pinning is containment rather than equality. Where the copy
    is verbatim the two agree exactly, on the files, on the lines, and on the share of the tree
    those lines occupy. Where the copy was renamed Symilar reports nothing and MCMR reports the
    block, which is the whole reason the detector normalizes at all.
    """

    def test_a_renamed_paste_is_found_where_symilar_sees_nothing(self, tmp_path: Path) -> None:
        """Symilar compares text, so renaming every local hides the copy from it completely."""
        paste(tmp_path, _RENAMED)

        oracle, _ = symilar_blocks(tmp_path)
        ours, table = mcmr_blocks(tmp_path)

        assert oracle == []
        assert ours == [{("module_a.py", 4, 13), ("module_b.py", 5, 14)}]
        assert value(pasted_block_copy_count, table, minimum_token_length=40) == 1

    def test_a_verbatim_paste_lands_on_the_lines_symilar_names(self, tmp_path: Path) -> None:
        """The strongest form of the claim, where neither reader has an excuse to differ."""
        paste(tmp_path, _ORIGINAL)

        oracle, _ = symilar_blocks(tmp_path)
        ours, _ = mcmr_blocks(tmp_path)

        assert oracle == [{("module_a.py", 4, 13), ("module_b.py", 5, 14)}]
        assert ours == oracle

    def test_the_repository_share_is_the_number_symilar_prints(self, tmp_path: Path) -> None:
        """Symilar divides duplicated lines by every line it read, and so does this rule."""
        paste(tmp_path, _ORIGINAL)

        _, share = symilar_blocks(tmp_path)
        _, table = mcmr_blocks(tmp_path)

        assert share == pytest.approx(37.04, abs=0.01)
        assert value(duplicated_repository_share, table) == pytest.approx(share, abs=0.01)

    def test_two_modules_that_share_no_block_are_quiet_in_both(self, tmp_path: Path) -> None:
        """A reader that finds duplication everywhere has told you nothing about anywhere."""
        (tmp_path / "module_a.py").write_text(_LEADING + _ORIGINAL)
        (tmp_path / "module_b.py").write_text(
            """def describe(name):
    return name.upper()


def widest(rows):
    return max(len(row.label) for row in rows)
"""
        )

        oracle, _ = symilar_blocks(tmp_path)
        ours, _ = mcmr_blocks(tmp_path)

        assert oracle == []
        assert ours == []
