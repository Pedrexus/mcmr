from ..... import rule
from .....facts import ArchitectureCharacteristicFact
from .....models import Percentage


@rule
def architecture_fitness_coverage(
    subject: ArchitectureCharacteristicFact,
    *,
    require_ci: bool = True,
    maximum_age_days: int = 30,
) -> Percentage:
    """Measure declared architecture characteristics with executable fitness evidence.

    Definition
    ----------
    Divide declared architecture characteristics protected by an objective, executable check,
    retained result, current observation date, owner, and scope by all declared characteristics.
    The result must come from CI when configured. Documentation or tool presence alone does not
    count as executable coverage.

    Evidence
    --------
    Findings link each quality characteristic to its objective, check, retained evidence, scope,
    owner, observation date, and CI or repeatable review path. The value is the percentage of
    declared characteristics carrying current executable evidence.

    Exceptions
    ----------
    Characteristics that cannot be automated may use a declared repeatable review with retained
    evidence when project policy permits it. A result older than `maximum_age_days` no longer
    counts as coverage, since a fitness function nobody has run recently is documentation. Setting
    `require_ci` to false accepts a check a person runs on demand, which is what a project without
    continuous integration has to do.

    Examples
    --------
    Eight of ten declared characteristics with current retained checks produce `80`. A written
    latency goal with no recent retained result does not count.

    References
    ----------
    Cites "Building Evolutionary Architectures", Fitness Functions
    Cites "Architecture Tradeoff Analysis Method"
    Cites "ISO IEC IEEE 42010", architecture descriptions
    """
    covered = sum(
        characteristic.has_objective
        and characteristic.has_executable_check
        and characteristic.has_retained_result
        and characteristic.has_owner
        and characteristic.has_scope
        and characteristic.observation_age_days <= maximum_age_days
        and (
            characteristic.is_automatable
            and (characteristic.is_in_ci or not require_ci)
            or not characteristic.is_automatable
            and characteristic.has_repeatable_review
        )
        for characteristic in subject.characteristics
    )
    return 100.0 * covered / len(subject.characteristics) if subject.characteristics else 0.0
