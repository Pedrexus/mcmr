from ..... import rule
from .....facts import ClassFact
from .....models import Choice, CountReport, Finding, Measurement, Reported, counted


@rule
def shared_model_placement(
    subject: ClassFact,
) -> CountReport:
    """Place reused model classes at the narrowest boundary justified by their imports.

    Definition
    ----------
    Detect declarative top-level Pydantic, house model, dataclass, and SQL table classes. A model
    must have at least two distinct importing modules before placement becomes actionable.
    Consumers confined to one package propose that package's `models.py`. Consumers spanning
    distinct packages propose one class file below the nearest common `models` package. The
    separate file-shape rule then requires one model class per shared package file. Classes with
    ordinary behavior are services even when they use a Pydantic foundation for configuration,
    so this placement rule excludes them. Pydantic validators, serializers, computed fields, and
    `model_post_init` remain declarative model behavior.

    Evidence
    --------
    Each finding cites the definition and its range, every ordinary module importing it by name,
    the exact proposed file, and how many importers that destination would put the model beside.
    The repair is a choice, since moving a type is a decision about ownership. Third-party
    model imports never match a project definition. Package
    `__init__.py` re-exports and modules holding nothing but imports do not establish a consumer
    location and are excluded from placement evidence. The value is the number of reused models
    whose current file is not the derived destination.

    Exceptions
    ----------
    A class directly declaring `ABC`, `Protocol`, `Registry`, or `Strategy` is a behavioral
    contract even when it also inherits a Pydantic foundation, so it is excluded. A configured
    analyzer, adapter, runner, or other service with ordinary methods is also excluded. Dynamic
    imports, module attribute access, inherited framework bases unknown to the configured
    foundations, and public consumers outside the analyzed project are not inferred. A domain
    model may remain beside its owner when moving it would create a dependency cycle. An already
    valid one-class file named after its model below a `models` package remains stable because
    package exports can have consumers outside the analyzed project.

    Examples
    --------
    An `OrderLine` used by two sibling modules under `shop.orders` belongs in
    `shop.orders.models`. A `Location` imported by unrelated backends, rules, and CLI packages
    belongs in `shop.models.location`. A request model with only one consumer stays beside its
    owner. A registered abstract backend and a `FrozenModel` service with an ordinary `run` method
    remain in their runtime modules.

    References
    ----------
    Cites "Pydantic documentation", models
    https://pydantic.dev/docs/validation/latest/concepts/models/
    Cites "The Python Standard Library", dataclasses
    https://docs.python.org/3/library/dataclasses.html
    Cites "A Philosophy of Software Design", chapters 4 and 5
    """
    misplaced = [
        item
        for item in subject.classes
        if item.is_declarative_model
        and not item.has_ordinary_behavior
        and len(set(item.importing_modules)) >= 2
        and bool(item.proposed_model_destination)
        and item.path != item.proposed_model_destination
    ]
    return Reported(
        value=len(misplaced),
        findings=tuple(
            Finding(
                message=(
                    f"`{item.name}` is a record with no behavior that "
                    f"{counted(len(set(item.importing_modules)), 'module')} import, and the "
                    f"file its readers share is `{item.proposed_model_destination}` rather "
                    f"than `{item.path}`"
                ),
                span=item.span or subject.span,
                measurements=(
                    Measurement(
                        name="modules importing it", value=len(set(item.importing_modules))
                    ),
                    Measurement(name="fields it declares", value=item.field_count),
                ),
                repair=Choice(
                    question=(
                        f"move `{item.name}` to `{item.proposed_model_destination}`, "
                        f"where its readers already are"
                    ),
                    options=(
                        "move the model to where it is used",
                        "keep it where the current file owns the concept",
                    ),
                ),
            )
            for item in misplaced
        ),
    )
