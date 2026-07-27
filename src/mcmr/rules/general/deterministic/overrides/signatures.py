import re
from functools import cached_property
from itertools import zip_longest
from typing import TYPE_CHECKING

from .....bases import FrozenFlexModel
from .....facts import MemberDeclaration, OverrideFact, ParameterDeclaration, ParameterKind

if TYPE_CHECKING:
    from typing import Self

# How a name says nobody was ever meant to pass this parameter. The spelling is the one Pylint
# reads for a dummy variable, because the messages this file serves are the ones Pylint states.
_PLACEHOLDER = re.compile(r"_+$|_[a-zA-Z0-9_]*[a-zA-Z0-9]$|dummy|ignored_|unused_")


def binding(declaration: MemberDeclaration, kind: ParameterKind) -> list[ParameterDeclaration]:
    """Return every parameter one declaration binds one way, in the order it states them."""
    return [item for item in declaration.parameters or [] if item.kind is kind]


def named_positions(declaration: MemberDeclaration) -> list[ParameterDeclaration]:
    """Return the positions a caller fills and may also name, past the receiver it never passes.

    A class method is handed its own class by the descriptor and no call site can pass it, so the
    first parameter of one is outside the signature anybody writes. An instance method is not the
    same, because reaching it through the class makes `self` an argument like any other.
    """
    held = binding(declaration, ParameterKind.POSITIONAL_OR_KEYWORD)
    handed_its_class = any(
        name.rsplit(".", 1)[-1] == "classmethod" for name in declaration.decorators
    )
    return held[1:] if handed_its_class else held


def optional_positions(declaration: MemberDeclaration) -> int:
    """Return how many positions of one declaration a caller is allowed to leave out."""
    return len(
        [
            item
            for item in declaration.parameters or []
            if item.has_default
            and item.kind in {ParameterKind.POSITIONAL_ONLY, ParameterKind.POSITIONAL_OR_KEYWORD}
        ]
    )


def unswallowed(
    held: list[ParameterDeclaration],
    answers: list[ParameterDeclaration],
    tail: list[ParameterDeclaration],
) -> list[ParameterDeclaration]:
    """Return the base parameters an override still has to answer under their own names.

    A `*args` or `**kwargs` accepts whatever the base accepted, so once the override writes one
    the base parameters it stopped naming are exactly the ones that tail stands for.
    """
    if not tail:
        return held
    answered = {item.name for item in answers}
    return [item for item in held if item.name in answered]


def counts_changed(held: list[ParameterDeclaration], answers: list[ParameterDeclaration]) -> bool:
    """Whether either list states a position the other side cannot answer.

    A position the override adds with a default extends the base rather than breaking it, since
    every existing call still binds what it always bound.
    """
    return any(
        answer is None or (first is None and not answer.has_default)
        for first, answer in zip_longest(held, answers)
    )


class SignatureChange(FrozenFlexModel):
    """Read one inherited declaration beside the declaration a subclass writes for it.

    The whole override family asks about the same two parameter lists, so the reading happens once
    here and each rule takes the part its own message means. A position a caller has to fill, a
    name a caller may pass, and a tail that swallows whatever is left over are three different
    promises, and only the kinds tell them apart.
    """

    inherited: MemberDeclaration
    override: MemberDeclaration

    @classmethod
    def across(cls, subject: OverrideFact) -> list[Self]:
        """Return every member of one base the subclass rewrote and a caller substitutes through.

        A name beginning with two underscores is skipped, since Python either rewrites it into the
        class that wrote it or calls it itself, and neither is a substitution anybody performs. A
        setter is skipped too, because the value assigned to it arrives as an argument the reader
        never wrote. Data wearing a method name states no parameters at all and belongs to the
        hiding rule instead.
        """
        return [
            cls(inherited=inherited, override=override)
            for inherited, override in subject.overrides
            if inherited.parameters is not None
            and override.parameters is not None
            and not inherited.name.startswith("__")
            and not any(name.endswith(".setter") for name in override.decorators)
        ]

    @cached_property
    def positions(self) -> tuple[list[ParameterDeclaration], list[ParameterDeclaration]]:
        """Return the positions a caller may also name, on the base side and the override side."""
        answers = named_positions(self.override)
        return (
            unswallowed(
                named_positions(self.inherited),
                answers,
                binding(self.override, ParameterKind.VAR_POSITIONAL),
            ),
            answers,
        )

    @cached_property
    def slots(self) -> tuple[list[ParameterDeclaration], list[ParameterDeclaration]]:
        """Return the positions no caller can name, as the base states them and the override.

        A positional-only parameter is a slot rather than a name, so dropping one breaks every
        caller while renaming one breaks nobody, and only how many there are is worth comparing.
        """
        answers = binding(self.override, ParameterKind.POSITIONAL_ONLY)
        return (
            unswallowed(
                binding(self.inherited, ParameterKind.POSITIONAL_ONLY),
                answers,
                binding(self.override, ParameterKind.VAR_POSITIONAL),
            ),
            answers,
        )

    @cached_property
    def keywords_changed(self) -> bool:
        """Whether either side names a keyword-only parameter the other cannot answer.

        A keyword-only parameter is reached by its name alone, so renaming one deletes it and adds
        another. That is why a changed name here counts as a changed set rather than as a rename.
        """
        answers = binding(self.override, ParameterKind.KEYWORD_ONLY)
        held = unswallowed(
            binding(self.inherited, ParameterKind.KEYWORD_ONLY),
            answers,
            binding(self.override, ParameterKind.VAR_KEYWORD),
        )
        stated = {item.name for item in answers}
        answered = {item.name for item in held}
        return any(item.name not in stated for item in held) or any(
            item.name not in answered and not item.has_default for item in answers
        )

    @cached_property
    def variadics_removed(self) -> bool:
        """Whether the base offered a tail that swallows arguments and the override dropped it."""
        return any(
            binding(self.inherited, kind) and not binding(self.override, kind)
            for kind in (ParameterKind.VAR_POSITIONAL, ParameterKind.VAR_KEYWORD)
        )

    @cached_property
    def renames(self) -> list[str]:
        """Return the base name of every position the override answers under a different one.

        A position one list ran out of is a changed count rather than a rename, so nothing is
        renamed once the two lists stop lining up.
        """
        held, answers = self.positions
        if counts_changed(held, answers):
            return []
        return [
            first.name
            for first, answer in zip_longest(held, answers)
            if first is not None
            and answer is not None
            and first.name != answer.name
            and _PLACEHOLDER.match(first.name) is None
            and _PLACEHOLDER.match(answer.name) is None
        ]

    @cached_property
    def renamed_parameters(self) -> int:
        """Return how many positions the override binds under a name the base never used."""
        return len(self.renames)

    @cached_property
    def differing_arguments(self) -> int:
        """Return how many ways a caller written against the base now fails against the override.

        A changed number of arguments is one answer whichever of the three lists it came from,
        because a caller meets one signature rather than three, and a swallowing tail the base
        offered and the override dropped is a second.
        """
        counted = (
            counts_changed(*self.positions) or counts_changed(*self.slots) or self.keywords_changed
        )
        return [counted, self.variadics_removed].count(True)

    @cached_property
    def required_what_the_base_defaulted(self) -> bool:
        """Whether an argument the base let a caller omit is now one the override demands.

        Nothing else about the two signatures differs, which is what makes this the quiet one.
        Every call keeps its shape and only the calls that relied on the default break. An
        override ending in a swallowing tail is left alone, because the tail still fills the gap.
        """
        return (
            not self.differing_arguments
            and not self.renames
            and not binding(self.override, ParameterKind.VAR_POSITIONAL)
            and optional_positions(self.override) < optional_positions(self.inherited)
        )
