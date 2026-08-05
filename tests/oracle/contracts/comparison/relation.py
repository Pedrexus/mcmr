from enum import StrEnum, auto


class Relation(StrEnum):
    """Say how what MCMR reported stands to what an upstream tool reported.

    MCMR is deliberately wider than an oracle in some places and narrower in others, and stating
    which is what keeps a difference visible instead of tuned away. An equality compares the two
    multisets, so a reader that found the same place twice as often has not agreed. A containment
    compares the distinct places instead, since a rule pinned to a declaration states one finding
    where a line-pinned reader states several and multiplicity is not a claim either can make about
    the other. A disjoint pair demands that both readers actually spoke, so it can never pass
    because one of them was silent. A union is where one MCMR rule answers what several upstream
    rules answer between them, and each of those is named rather than merged behind one selection.
    """

    EQUALS = auto()
    SUBSET = auto()
    SUPERSET = auto()
    DISJOINT = auto()
    UNION = auto()

    def stated_between(self, tools: int) -> bool:
        """Whether this relation can be stated between MCMR and that many upstream rules."""
        return tools >= 2 if self is Relation.UNION else tools == 1
