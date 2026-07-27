from typing import Literal

from ..... import rule
from .....facts import ModuleFact


@rule
async def module_cohesion(
    subject: ModuleFact,
) -> Literal["cohesive", "mixed", "intentional_integration", "uncertain"]:
    """Assess whether a module mixes unrelated responsibilities.

    Definition
    ----------
    Independently establish change causes, member clusters, a single domain outcome, and an
    integration-boundary purpose. A deterministic table maps those cited facts to the category.

    Evidence
    --------
    Findings retain the model reasoning and every valid cited evidence identifier.

    Exceptions
    ----------
    Composition roots, facades, adapters, and deliberate integration modules may coordinate
    several systems while retaining one architectural responsibility.

    Examples
    --------
    Parsing invoices and sending unrelated email campaigns in one module is `mixed`. A composition
    root wiring both systems is `intentional_integration`.

    References
    ----------
    Cites "Clean Architecture", chapters 7 and 10
    Cites "Agile Software Development", chapter 8
    Cites "A Philosophy of Software Design", chapter 10
    """
    responsibilities = {
        member.responsibility for member in subject.members if member.responsibility
    }
    if not responsibilities:
        return "uncertain"
    if len(responsibilities) == 1:
        return "cohesive"
    return "intentional_integration" if subject.is_integration_boundary else "mixed"
