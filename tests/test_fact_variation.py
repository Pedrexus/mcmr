from typing import TYPE_CHECKING, get_args

import pytest

from mcmr.bases import FrozenFlexModel
from mcmr.facts import Fact, NodeRef, SourceSpan, SymbolRef
from mcmr.kernel import VENDORED, Kernel, buildable
from tests.conftest import BINARY, ROOT, needs_kernel, written

if TYPE_CHECKING:
    from pathlib import Path

# How far into a fact this reads. A fact holds one list of records and each record holds its own,
# which is where every fabricated field found so far has been, and below that the shapes are the
# addressing plumbing a rule reaches through rather than evidence it judges.
DEPTH = 2

# Where a fact is rather than what it says. A span, a node handle, and a symbol reference exist so
# a fix can point at source, and their kinds and identifiers are constant by construction, so
# reading them here would fill the ledger with entries nobody can act on.
ADDRESS = (NodeRef, SourceSpan, SymbolRef)
ENVELOPE = frozenset(Fact.model_fields)

# What a field holding records rather than a value is recorded as. A rule reads the records, so a
# list that always holds at least one is a filled family and never a finding, while one that is
# empty every time is a rule reading nothing at all. Only the second is what this ledger is for.
STATED = "stated"
ABSENT = "absent"

# The second half of the corpus, and the reason it is only the second half. The first half is this
# repository, which is real code nobody wrote to satisfy this test, and that is what makes a field
# constant across it evidence rather than an artifact of a fixture. What the repository cannot do
# is state a shape it does not hold, so a field is constant here for two very different reasons and
# no scan of one project can tell those apart.
#
# This fixture supplies the missing shapes and nothing else. It is a second project, so the
# manifest facts have a second answer to give. It declares an exception two ordinary modules
# import, local collections read every way that settles or unsettles a representation, and a
# dispatch chain whose arms differ in size, so the four providers corrected alongside this test
# have to vary or the ledger below turns red. It deliberately does not try to exercise every
# family, because a fixture written to move a field proves only that the fixture moves it. Wherever
# a field stays constant the entry says which of the two reasons it is.
FIXTURE: dict[str, str] = {
    "pyproject.toml": (
        "[project]\n"
        'name = "shop"\n'
        'requires-python = ">=3.12"\n\n'
        "[tool.pytest.ini_options]\n"
        'addopts = "-q --strict-config"\n'
        'import_mode = "importlib"\n'
        'anyio_mode = "strict"\n\n'
        "[tool.ruff]\n"
        'target-version = "py312"\n'
    ),
    "chefe.toml": (
        "[tasks]\n"
        'setup = "sudo apt-get install -y libshop"\n'
        'lint = "ruff check ."\n'
        'typecheck = "mypy src"\n'
        'test = "python -m pytest"\n'
        'build = "python -m build --outdir .dist"\n'
        'shell = "docker run -it shop bash"\n\n'
        "[envs.ci.tasks]\n"
        'test = "python -m pytest -x"\n'
    ),
    "shop/__init__.py": "",
    "shop/errors.py": (
        "class OrderError(Exception):\n"
        '    """One order could not be placed."""\n\n\n'
        "class OrderLineError(OrderError):\n"
        '    """One line of an order could not be placed."""\n'
    ),
    # A drawn separator is what `repeated_literal` exists to find, and the house style forbids
    # one, so the only place this repository can hold the shape is a project it writes on purpose.
    "shop/banner.py": (
        "def rule_off() -> str:\n"
        '    """Return the line a report draws under its heading."""\n'
        '    return "===="\n'
    ),
    "shop/service.py": (
        "from .errors import OrderError\n\n"
        'FORMATS = ("json", "toml")\n\n\n'
        "class Ledger:\n"
        '    """Hold what one shop recorded."""\n\n'
        "    def __init__(self, rows: list[str]) -> None:\n"
        "        self.rows = rows\n\n"
        "    @property\n"
        "    def size(self) -> int:\n"
        '        """How many rows the ledger holds."""\n'
        "        return len(self.rows)\n\n"
        "    def __len__(self) -> int:\n"
        "        return self.size\n\n"
        "    def widest(self) -> int:\n"
        '        """Return the longest row, reached through the name this class states."""\n'
        "        return Ledger.longest(self.rows)\n\n"
        "    @staticmethod\n"
        "    def longest(rows: list[str]) -> int:\n"
        '        """Return how long the longest of these rows is."""\n'
        "        return max((len(row) for row in rows), default=0)\n\n\n"
        "def render(kind: str, value: str) -> str:\n"
        '    """Render one value the way its kind asks for."""\n'
        '    if kind == "json":\n'
        "        return value\n"
        '    elif kind == "toml":\n'
        "        head = value.strip()\n"
        "        return head\n"
        '    elif kind == "yaml":\n'
        "        return value.upper()\n"
        "    else:\n"
        '        return ""\n\n\n'
        "def widen(names: list[str]) -> list[str]:\n"
        '    """Widen every name, reading the suffixes only by iterating them."""\n'
        '    suffixes = ["json", "toml"]\n'
        '    return [f"{name}.{suffix}" for name in names for suffix in suffixes]\n\n\n'
        "def known(name: str) -> bool:\n"
        '    """Whether one name is one this shop writes, read only as a membership test."""\n'
        '    allowed = ["json", "toml"]\n'
        "    return name in allowed\n\n\n"
        "def leading(rows: list[str]) -> str:\n"
        '    """Return the first row, which indexes the literal and settles nothing."""\n'
        '    order = ["json", "toml"]\n'
        "    return order[0] + rows[0]\n\n\n"
        "def place(kind: str) -> None:\n"
        '    """Place one order, or say why it could not be placed."""\n'
        "    if kind not in FORMATS:\n"
        "        raise OrderError(kind)\n"
    ),
    "shop/api.py": (
        "from .errors import OrderError\n"
        "from .service import place\n\n\n"
        "def submit(kind: str) -> str:\n"
        '    """Submit one order and name what came back."""\n'
        "    try:\n"
        "        place(kind)\n"
        "    except OrderError:\n"
        '        return "rejected"\n'
        '    return "placed"\n'
    ),
    "shop/jobs.py": (
        "from .errors import OrderError\n"
        "from .service import place\n\n\n"
        "def sweep(kinds: list[str]) -> int:\n"
        '    """Place every order it can and count the ones it could not."""\n'
        "    refused = 0\n"
        "    # placed = [place(kind) for kind in kinds]\n"
        "    for kind in kinds:  # noqa: PERF203\n"
        "        try:\n"
        "            place(kind)\n"
        "        except OrderError:\n"
        "            refused += 1\n"
        "    return refused\n"
    ),
    "shop/status.py": (
        "from enum import IntEnum, StrEnum, auto\n\n\n"
        "class Stage(StrEnum):\n"
        '    """Name where one order sits."""\n\n'
        "    PLACED = auto()\n"
        "    SHIPPED = auto()\n\n\n"
        "class Priority(IntEnum):\n"
        '    """Name how urgently one order ships."""\n\n'
        "    LOW = 1\n"
        "    HIGH = 2\n\n\n"
        "def waiting(stage: str) -> bool:\n"
        '    """Whether one stage is still waiting on somebody."""\n'
        "    if stage == Stage.PLACED:\n"
        "        return True\n"
        "    elif stage == Stage.SHIPPED:\n"
        "        return False\n"
        "    return False\n"
    ),
    "shop/lookup.py": (
        "def label(wanted: str) -> str:\n"
        '    """Read one label out of a table nothing but the lookup reads."""\n'
        '    rows = [("open", "Open"), ("closed", "Closed")]\n'
        "    for key, value in rows:\n"
        "        if key == wanted:\n"
        "            return value\n"
        '    return ""\n\n\n'
        "def widths(wanted: str) -> int:\n"
        '    """Read a table the body also measures, which no mapping states more clearly."""\n'
        '    rows = [("open", 4), ("open", 6), ("closed", 6)]\n'
        "    total = len(rows)\n"
        "    for key, value in rows:\n"
        "        if key == wanted:\n"
        "            return value\n"
        "    return total\n\n\n"
        "def totals(wanted: str) -> int:\n"
        '    """Rebind one table, which is what stops a mapping from stating it."""\n'
        '    rows = [("open", 1), ("closed", 2)]\n'
        '    rows = [*rows, ("held", 3)]\n'
        "    for key, value in rows:\n"
        "        if key == wanted:\n"
        "            return value\n"
        "    return 0\n\n\n"
        "class Receipt:\n"
        '    """Hold what one order was charged, and refuse a charge nobody can pay."""\n\n'
        '    def __init__(self, order: str, amount: int = 0, currency: str = "JPY") -> None:\n'
        "        if amount < 0:\n"
        "            raise ValueError(order)\n"
        "        self.order = order\n"
        "        self.amount = amount\n"
        "        self.currency = currency\n\n"
        "    def __repr__(self) -> str:\n"
        '        return f"{self.order}:{self.amount}"\n'
    ),
    "shop/test_shop.py": (
        "from typing import Annotated\n\n"
        "from pydantic import Field\n\n"
        "from .lookup import label\n"
        "from .service import render\n\n"
        "SEEN: list[str] = []\n\n\n"
        'def charge(amount: Annotated[int, Field(description="what one line cost")]) -> int:\n'
        '    """Take a price whose metadata describes this field and nothing else."""\n'
        "    return amount\n\n\n"
        "def helper(value: str) -> str:\n"
        '    """Not a test, and the test below it is not one either."""\n\n'
        "    def test_inner() -> None:\n"
        "        assert value\n\n"
        "    return value\n\n\n"
        "def test_labels_are_read_from_the_table() -> None:\n"
        '    """A collected test that walks its own cases and checks each one."""\n'
        '    for key in ["open", "closed"]:\n'
        "        assert label(key)\n\n\n"
        "def test_renders_every_kind() -> None:\n"
        '    """A collected test that writes to state the module holds."""\n'
        '    SEEN.append(render("json", "a"))  # noqa: PERF401 reason=one call is not a loop '
        "since=2020-01-02 expires=2099-01-01\n"
        "    assert SEEN\n"
    ),
}

# The three ways a field comes to hold one answer forever. The first two are the defect this ledger
# exists for, and the third is what the corpus cannot reach, which is a statement about the corpus
# rather than about the kernel and has to be told apart from the other two on purpose.
UNWRITTEN = "no frontend writes it, so every fact takes the model default"
LITERAL = "every frontend states this same literal"
UNSHAPED = "derived, and this corpus states no shape that moves it"

# A family the corpus produces no facts for at all, with the reason nothing states one. This is the
# same defect one level up, because a family answering nothing is a rule reading an empty stream,
# which reports zero and reads exactly like a clean repository.
UNFILLED: dict[str, str] = {
    "KernelLaunchFact": ("only a CUDA source states a launch and this corpus holds no CUDA"),
    "ModuleSurfaceFact": (
        "only the TypeScript frontend fills it and this corpus holds no TypeScript"
    ),
    "RepositoryHistoryFact": (
        "read from the version control log rather than from source, and this checkout has "
        "no commits yet"
    ),
}

# Every fact field this corpus never moves, with the reason. A rule reading one of these reads the
# same answer forever, so each entry says whether no frontend writes the field at all, whether
# every frontend writes the same literal, or whether the field is derived and the corpus holds no
# shape that would move it. The first two are a rule that cannot fire, which is a defect this
# catalog has now produced ten times, and the ledger is here so the eleventh fails a test rather
# than reading like a clean repository.
INVARIANT: dict[str, str] = {
    "CallFact.calls[].arguments[].resolved_type": UNWRITTEN,
    "CallFact.calls[].assigned_target": UNWRITTEN,
    "CallFact.calls[].enclosing_is_async": UNWRITTEN,
    "CallFact.calls[].has_ambiguous_alias": UNWRITTEN,
    "CallFact.calls[].has_starred_arguments": UNWRITTEN,
    "CallFact.calls[].is_constructor": UNWRITTEN,
    "CallFact.calls[].is_decorator_factory": UNWRITTEN,
    "CallFact.calls[].is_external": UNWRITTEN,
    "CallFact.calls[].is_first_party": UNWRITTEN,
    "CallFact.calls[].is_shadowed": UNWRITTEN,
    "CallFact.calls[].is_standard_library": UNWRITTEN,
    "CallFact.calls[].receiver.arguments": UNWRITTEN,
    "CallFact.calls[].receiver.entries": UNWRITTEN,
    "CallFact.calls[].receiver.literal_kind": UNWRITTEN,
    "CallFact.calls[].receiver.resolved_type": UNWRITTEN,
    "ClassFact.classes[].base_is_removable_overlap": (
        "derived, and no class in the corpus has a single base kept only for it"
    ),
    "ClassFact.classes[].class_keywords": (
        "derived, and no class in the corpus states a metaclass or any other class keyword"
    ),
    "ClassFact.classes[].duplicate_component_alias_count": (
        "derived, and no constructor in the corpus copies a field off a component it also keeps"
    ),
    "ClassFact.classes[].has_noncooperative_concrete_collision": (
        "derived, and no class in the corpus takes one concrete member from two direct bases"
    ),
    "ClassFact.classes[].has_redundant_direct_base": (
        "derived, and no class in the corpus names a base one of its other bases already inherits"
    ),
    "ClassFact.classes[].inherits_approved_model_foundation": (
        "derived, and every model in the corpus derives this project's own base rather than one "
        "an approved foundation module states"
    ),
    "ClassFact.classes[].is_exported": (
        "derived, and no module in the corpus lists a class in `__all__` or re-exports one "
        "through a package initializer"
    ),
    "ClassFact.classes[].is_pass_through_layer": (
        "derived, and every subclass in the corpus either states a body or documents why it holds "
        "none"
    ),
    "ClassFact.classes[].methods[].region": (
        "derived, and no class in the corpus opens a second ordered section with a region marker"
    ),
    "ClassFact.classes[].only_cross_module_reference_is_subclass": (
        "derived, and every class the corpus shares across modules is reached for more than one "
        "declaration"
    ),
    "ClassFact.model_files": (
        "derived, and no directory in the corpus is a shared models package holding a data model"
    ),
    "CloneGroupFact.repository_line_count": (
        "one number per repository, and only this repository states a clone group at all"
    ),
    "ComprehensionFact.set_loop_candidates": (
        "derived, and no file in the corpus fills a set through a bare loop"
    ),
    "EnumFact.enums[].overrides_generate_next_value": (
        "derived, and no enumeration in the corpus writes its own value generator"
    ),
    "EnumFact.files": (
        "whether a shared `enums` package holds one enumeration per module is a claim about "
        "the package, so no per-file builder can answer it and this one leaves the list empty"
    ),
    "EnumFact.scopes": (
        "where a reused enumeration belongs is decided by every module that imports it, so no "
        "per-file builder can answer it and this one leaves the list empty"
    ),
    "FunctionFact.created_task_count": (
        "derived, and no callable in the corpus schedules work through the asyncio its own file "
        "imported"
    ),
    "FunctionFact.gather_consumes_created_tasks": (
        "derived, and no callable in the corpus gathers tasks it created itself"
    ),
    "FunctionFact.gather_returns_exceptions": (
        "derived, and no callable in the corpus gathers anything at all"
    ),
    "FunctionFact.has_task_group": (
        "derived, and no callable in the corpus opens an asyncio task group"
    ),
    "FunctionFact.has_tensor_dtype_semantics": (
        "derived, and no signature in the corpus annotates a tensor"
    ),
    "FunctionFact.has_tensor_shape_semantics": (
        "derived, and no signature in the corpus annotates a tensor"
    ),
    "FunctionFact.is_overload": (
        "derived, and no callable in the corpus is declared as an overload"
    ),
    "FunctionFact.is_pass_body": (
        "derived, and no callable in the corpus has a body of exactly one `pass`"
    ),
    "FunctionFact.is_raise_body": (
        "derived, and no callable in the corpus has a body of exactly one `raise`"
    ),
    "FunctionFact.parameters[].is_positional_only": (
        "derived, and no signature in the corpus writes a positional-only marker"
    ),
    "FunctionFact.recognized_tensor_roles": (
        "derived, and no signature in the corpus annotates a tensor"
    ),
    "ImportBindingFact.has_documented_side_effect": (
        "derived, and no import in the corpus sits under a `try` that handles an import failure"
    ),
    "ImportBindingFact.has_private_module_component": (
        "derived, and no import in the corpus names a private package component"
    ),
    "ImportBindingFact.is_generated": UNWRITTEN,
    "ImportBindingFact.is_private_member": (
        "derived, and no import in the corpus binds a private member"
    ),
    "ImportBindingFact.is_private_uppercase_constant": UNWRITTEN,
    "ImportBindingFact.is_type_only": (
        "only the TypeScript frontend writes it and this corpus holds no TypeScript"
    ),
    "ImportBindingFact.is_vendored": UNWRITTEN,
    "ImportBindingFact.is_wildcard": ("derived, and no module in the corpus states a star import"),
    "InteropFact.mechanism": (
        "derived, and both seams this corpus states are a binary a manifest declares"
    ),
    "InteropFact.references[].is_literal": UNWRITTEN,
    "InteropFact.referencing_languages": (
        "derived, and both seams this corpus states are reached from the same two languages"
    ),
    "ModuleFact.constant_placements": UNWRITTEN,
    "ModuleFact.is_integration_boundary": UNWRITTEN,
    "ModuleFact.members[].responsibility": LITERAL,
    "OverrideFact.base_decorators": (
        "derived from the graph, and no override pair in the corpus decorates its base"
    ),
    "OverrideFact.derived_decorators": (
        "derived from the graph, and no override pair in the corpus decorates its override"
    ),
    "OverrideFact.initializer_calls": (
        "derived from the graph, and no override pair in the corpus is a constructor"
    ),
    "ProjectConfigurationFact.assignments": LITERAL,
    "ProjectConfigurationFact.python_target.per_file_target_minors": LITERAL,
    "PydanticModelFact.models[].validators": (
        "derived, and no model the corpus declares carries a validator"
    ),
    "QueryFact.operations[].expire_on_commit": (
        "derived from the keywords a session factory carries, and the one database operation "
        "the corpus states is a commit rather than a factory"
    ),
    "QueryFact.operations[].framework": (
        "derived, and the one database operation the corpus states is a SQLAlchemy commit"
    ),
    "QueryFact.operations[].has_execution_options": (
        "belongs to the primary-key lookup chain this provider does not recognize yet, so no "
        "operation it states can carry one"
    ),
    "QueryFact.operations[].has_primary_key_equality": (
        "belongs to the primary-key lookup chain this provider does not recognize yet, so no "
        "operation it states can carry one"
    ),
    "QueryFact.operations[].has_unknown_keywords": (
        "derived from the keywords a session factory carries, and the one database operation "
        "the corpus states carries none"
    ),
    "QueryFact.operations[].is_inside_loop": (
        "derived, and the one database operation the corpus states is not inside a loop"
    ),
    "QueryFact.operations[].kind": (
        "derived, and the one database operation the corpus states is a commit"
    ),
    "QueryFact.operations[].selected_expression_count": (
        "derived, and the one database operation the corpus states takes two arguments"
    ),
    "RouteFact.frameworks": ("derived, and no framework in the corpus declares a route"),
    "RouteFact.routes": ("derived, and no framework in the corpus declares a route"),
    "RustSurfaceFact.annotations[].beyond": (
        "derived, and no lifetime the corpus states reaches past the signature that binds it"
    ),
    "RustSurfaceFact.annotations[].receiver": (
        "derived, and no lifetime the corpus states appears on a receiver"
    ),
    "SymbolFact.typing_scopes": (
        "which type declarations a directory reuses is a question about every module at once, "
        "so no per-file builder can answer it and this one leaves the list empty"
    ),
    "SymbolReachFact.declarations[].import_count": UNWRITTEN,
    "TestSuiteFact.asyncio_mode": (
        "derived, and neither manifest in the corpus configures an asyncio mode"
    ),
    "TestSuiteFact.quarantined_tests": LITERAL,
    "TryBlockFact.regions[].has_following_raising_operation": (
        "derived, and every protected region in the corpus holds more than leading assignments"
    ),
    "TryBlockFact.regions[].leading_literal_assignment_count": (
        "derived, and no protected region in the corpus opens with a literal assignment"
    ),
    "TestFunctionFact.tests[].calls[].has_ambiguous_alias": UNWRITTEN,
    "TestFunctionFact.tests[].calls[].is_decorator_factory": UNWRITTEN,
    "TestFunctionFact.tests[].calls[].is_external": UNWRITTEN,
    "TestFunctionFact.tests[].calls[].is_first_party": UNWRITTEN,
    "TestFunctionFact.tests[].calls[].is_shadowed": UNWRITTEN,
    "TestFunctionFact.tests[].calls[].is_standard_library": UNWRITTEN,
    "WaiverFact.waivers[].is_overly_broad": (
        "derived, and every suppression in the corpus names the rule it waives"
    ),
}


# The third project of the corpus, which declares nothing about itself at all. Every root the
# ledger reads carries a manifest, and that is what let a whole family be fabricated rather than a
# single field: over a directory holding one source file and no manifest, the kernel stated a
# configuration fact at `pyproject.toml:1:1` and a task fact at `chefe.toml:1:1`, both empty, both
# claiming to be Python, and two rules then failed against files the repository does not contain.
#
# It stays out of the ledger deliberately. A field the ledger excuses is one no corpus moved, and a
# root written to lack something moves fields for a reason about the fixture rather than about the
# kernel. What this root is for is the question the ledger cannot ask, which is whether a fact
# names a place that exists.
MANIFESTLESS: dict[str, str] = {
    "src/engine.cuh": (
        "#pragma once\n\n"
        "// TODO: hand the merge its own stream\n"
        "struct Engine {\n"
        "  int limit;\n"
        "};\n\n"
        "__global__ void scale(float* data, int count);\n"
    ),
    "src/engine.cu": (
        '#include "engine.cuh"\n\n'
        "__global__ void scale(float* data, int count) {\n"
        "  int index = 0;\n"
        "  if (index < count) {\n"
        "    data[index] = data[index] * 2.0f;\n"
        "  }\n"
        "}\n\n"
        "void run(float* data, int count) {\n"
        "  scale<<<count, 256>>>(data, count);\n"
        "}\n"
    ),
}


@pytest.fixture(scope="module")
def fixture_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write the second project of the corpus, which states what this repository does not."""
    return written(tmp_path_factory.mktemp("variation"), FIXTURE)


@pytest.fixture(scope="module")
def manifestless_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write the third project of the corpus, which declares nothing about itself."""
    return written(tmp_path_factory.mktemp("manifestless"), MANIFESTLESS)


@pytest.fixture(scope="module")
def observed(fixture_root: Path) -> dict[str, set[str]]:
    """Return every distinct value each fact field took across the whole corpus."""
    seen: dict[str, set[str]] = {}
    for root in (ROOT, fixture_root):
        collect(root, seen)
    return seen


def collect(root: Path, seen: dict[str, set[str]]) -> None:
    """Build every family the kernel knows over one root and read what each field held."""
    families = buildable()
    kernel = Kernel(binary=BINARY, root=root, exclude=VENDORED)
    workspace = kernel.build(sorted(families), families)
    for name, family in families.items():
        for fact in workspace.stream(family):
            record(name, fact, seen, 0)


def record(prefix: str, model: FrozenFlexModel, seen: dict[str, set[str]], depth: int) -> None:
    """Record what one model held, one field at a time, down to the depth a rule reads."""
    for name, field in type(model).model_fields.items():
        if depth == 0 and name in ENVELOPE:
            continue
        inner = held(field.annotation)
        if inner is not None and issubclass(inner, ADDRESS):
            continue
        value = getattr(model, name)
        path = f"{prefix}.{name}"
        if inner is None:
            seen.setdefault(path, set()).add(repr(value))
            continue
        stated = bool(value) if isinstance(value, list) else value is not None
        seen.setdefault(path, set()).add(STATED if stated else ABSENT)
        if not stated or depth >= DEPTH:
            continue
        for item in value if isinstance(value, list) else [value]:
            record(f"{path}[]" if isinstance(value, list) else path, item, seen, depth + 1)


def unmoved(observed: dict[str, set[str]]) -> set[str]:
    """Return every field the corpus never moved, which is the ledger this test holds."""
    return {path for path, values in observed.items() if len(values) == 1 and values != {STATED}}


def held(annotation: type | None) -> type[FrozenFlexModel] | None:
    """Return the model one annotation carries, looking through a list and through a union."""
    if isinstance(annotation, type):
        return annotation if issubclass(annotation, FrozenFlexModel) else None
    return next(
        (found for argument in get_args(annotation) if (found := held(argument)) is not None),
        None,
    )


@needs_kernel
def test_no_provider_states_the_same_thing_forever_without_a_recorded_reason(
    observed: dict[str, set[str]],
) -> None:
    """A field one corpus never moves is either invariant or fabricated, and which one is a claim.

    A provider writing a literal is indistinguishable from a provider deriving a value that
    happens to agree, right up until a rule reads it and answers the same thing forever. So the
    ledger fails in both directions. A newly constant field has to be written down with its reason,
    and a field that starts varying has to have its entry taken out, because an entry nobody
    removed is the stale allowance a reader would trust.
    """
    assert sorted(unmoved(observed) - set(INVARIANT)) == []
    assert sorted(set(INVARIANT) - unmoved(observed)) == []


@needs_kernel
def test_no_family_answers_nothing_without_a_recorded_reason(
    observed: dict[str, set[str]],
) -> None:
    """A family nothing fills is a rule reading an empty stream, which reads as a clean repository.

    That is the same defect one level up, so it is recorded the same way and held to the same
    ledger from both sides.
    """
    silent = {
        name for name in buildable() if not any(path.startswith(f"{name}.") for path in observed)
    }

    assert sorted(silent - set(UNFILLED)) == []
    assert sorted(set(UNFILLED) - silent) == []


def test_every_recorded_entry_names_something_real_and_says_why() -> None:
    """The ledger cannot record a field no family declares, and cannot record one without a reason.

    Without this the tables only grow, and an entry naming a field somebody renamed would keep
    excusing a field that no longer exists.
    """
    families = set(buildable())

    assert set(UNFILLED) <= families
    assert {path.split(".")[0] for path in INVARIANT} <= families
    assert all(reason for reason in {**UNFILLED, **INVARIANT}.values())


@needs_kernel
@pytest.mark.parametrize("corpus", ["fixture_root", "manifestless_root"])
def test_every_fact_names_a_place_the_repository_holds(
    corpus: str, request: pytest.FixtureRequest
) -> None:
    """A fact pointing at a file nobody wrote is the fabrication defect one level up.

    The ledger asks whether a field ever moved, which cannot see a whole fact that had no evidence
    behind it. A location can be checked directly, and it is the same claim in both directions. A
    repository declaring no manifest gets no manifest facts, and a repository declaring one gets
    facts at the file it declared. Without the third corpus the first half of that never runs,
    since every project the ledger reads carries a manifest.
    """
    root = request.getfixturevalue(corpus)
    families = buildable()
    workspace = Kernel(binary=BINARY, root=root, exclude=VENDORED).build(
        sorted(families), families
    )
    stated = {fact.span.path for family in families.values() for fact in workspace.stream(family)}

    assert stated
    assert sorted(path for path in stated if not (root / path).exists()) == []
