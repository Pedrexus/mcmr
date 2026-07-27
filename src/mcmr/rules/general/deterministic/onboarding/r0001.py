from ..... import rule
from .....facts import OnboardingTaskFact
from .....models import Percentage


@rule
def onboarding_readiness(
    subject: OnboardingTaskFact,
) -> Percentage:
    """Measure whether a newcomer can perform essential project work.

    Definition
    ----------
    Verify each configured onboarding capability through current commands and concise
    guidance, then return the percentage of required capabilities that were verified.

    Evidence
    --------
    Findings retain the attempted command, guidance location, outcome, and missing prerequisite.
    The value is the percentage of required capabilities verified through a current command.

    Exceptions
    ----------
    Restricted production access is not required when a safe local or staging path exists.

    Examples
    --------
    Four verified capabilities among five produce `80`. Mentioning a stale setup command
    does not satisfy the setup capability.

    References
    ----------
    Cites "Software Engineering at Google", knowledge sharing
    Cites "GitHub documentation", contributing guidelines
    """
    return subject.capabilities.coverage("current_command", "concise_guidance")
