from ..... import rule
from .....facts import ImportBindingFact
from .....models import Remove, SourceRewrite


@rule
def deprecated_future_annotations(subject: ImportBindingFact, *, python_minor: int = 14) -> bool:
    """Detect the deprecated annotations future import for Python 3.14 projects.

    Definition
    ----------
    Report `from __future__ import annotations` when the configured minimum Python 3 minor
    version is 14 or newer. Python 3.14 provides deferred annotation evaluation through PEP
    649 and PEP 749, while the older future import retains PEP 563 stringization semantics and
    is deprecated. A plain one-line import receives a review fix that removes the full line.

    Evidence
    --------
    Each finding identifies the future import and includes a source-preserving byte edit when
    removal does not share a line or statement with other code.

    Exceptions
    ----------
    Keep the import temporarily when software intentionally depends on PEP 563 stringized runtime
    annotations. The fix requires review because removal changes runtime annotation representation
    even though ordinary static annotations remain valid. `python_minor` is the Python 3 minor
    version the project targets, so a project still supporting an older interpreter lowers it and
    the rule stops asking for syntax that release does not have.

    Examples
    --------
    A module targeting Python 3.14 that states `from __future__ import annotations` returns `true`
    and can drop that line. The same module without the import returns `false`, and so does any
    module in a project whose `python_minor` is below 14.

    References
    ----------
    Adapts Pylint W0410 misplaced-future
    Cites "What's New In Python", `from __future__ import annotations`
    Cites "PEP 649, Deferred Evaluation of Annotations"
    Cites "PEP 749, Implementing PEP 649", the future of PEP 563
    """
    imported = subject.imported_name or subject.name
    return python_minor >= 14 and subject.module == "__future__" and imported == "annotations"


@deprecated_future_annotations.fix(is_default=True)
def remove_future_annotations(
    subject: ImportBindingFact, *, python_minor: int = 14
) -> list[SourceRewrite]:
    """Remove an annotations import the target Python version no longer needs."""
    return [Remove(target=subject.declaration)] if subject.declaration else []
