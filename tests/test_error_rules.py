from mcmr.facts import SyntaxNode
from mcmr.rules.general.deterministic.errors.r0001 import swallowed_error
from mcmr.rules.general.deterministic.errors.r0002 import raise_without_cause
from mcmr.rules.general.deterministic.errors.r0003 import vanilla_error_type
from mcmr.rules.general.deterministic.errors.r0004 import raise_inside_guarded_region
from tests.conftest import Declaration

DECLARED = Declaration(
    path="src/mailer.py", qualname="deliver", source="def deliver(message):\n    ...\n"
)
RUSTY = DECLARED.model_copy(update={"language": "rust"})


def guard(text: str, *children: SyntaxNode) -> SyntaxNode:
    """Build one guard carrying the source a frontend hands a rule, plus its protected body."""
    return SyntaxNode(kind="guard", text=text, children=list(children))


def raised(*children: SyntaxNode) -> SyntaxNode:
    """Build one raise stating the type it constructs, or nothing when it re-raises."""
    return SyntaxNode(kind="raise", children=list(children))


def call(name: str) -> SyntaxNode:
    """Build one call node, which is how a raise names the type it builds."""
    return SyntaxNode(kind="call", name=name)


def test_a_handler_that_answers_with_nothing_throws_the_failure_away() -> None:
    """The program then runs on state the failed step never finished writing.

    Anything at all in the body means the failure reached a person or a fallback, while a comment
    only claims it did and the run carries on as if nothing had gone wrong. One rule reads the
    Python guard and the braced one through the same vocabulary, whichever way the braces sit.
    """
    dropped = DECLARED.of(
        guard("try:\n    deliver(message)\nexcept TimeoutError:\n    pass"),
        guard(
            "for message in queue:\n    try:\n        deliver(message)\n"
            "    except TimeoutError:\n        continue"
        ),
    )
    answered = DECLARED.of(
        guard(
            "try:\n    deliver(message)\nexcept TimeoutError as error:\n"
            "    logger.warning(error)\n    queue.retry(message)"
        )
    )
    inline = DECLARED.of(guard("try {\n    deliver(message);\n} catch (error) {}"))
    allman = DECLARED.of(
        guard("try\n{\n    deliver(message);\n}\ncatch (const Timeout& error)\n{\n}")
    )
    braced_answer = DECLARED.of(
        guard(
            "try\n{\n    deliver(message);\n}\ncatch (const Timeout& error)\n{\n    log(error);\n}"
        )
    )
    excused = DECLARED.of(
        guard("try {\n    deliver(message);\n} catch (error) {\n    // nothing to do here\n}")
    )

    assert swallowed_error(dropped) == 2
    assert swallowed_error(dropped, inert=("pass",)) == 1
    assert swallowed_error(answered) == 0
    assert swallowed_error(inline) == 1
    assert swallowed_error(allman) == 1
    assert swallowed_error(braced_answer) == 0
    assert swallowed_error(excused) == 1


def test_a_result_bound_to_the_throwaway_name_is_discarded_too() -> None:
    """`let _ = fallible()` drops a failure exactly the way an empty handler does.

    Only where a language hands failures back as values, since `_ = risky()` in Python drops a
    value while the exception carries on regardless.
    """
    bindings = (
        SyntaxNode(kind="binding", text="let _ = deliver(message);", children=[call("deliver")]),
        SyntaxNode(
            kind="binding", name="raw", text="raw = deliver(message)", children=[call("deliver")]
        ),
        SyntaxNode(
            kind="binding", name="_", text="_ = 3", children=[SyntaxNode(kind="literal", text="3")]
        ),
    )
    destructured = SyntaxNode(
        kind="binding",
        text="let Some((_, inside)) = path.split_once(anchor)",
        children=[call("split_once")],
    )
    discarding = RUSTY.of(*bindings, destructured)
    throwing = DECLARED.of(
        SyntaxNode(
            kind="binding", name="_", text="_ = deliver(message)", children=[call("deliver")]
        )
    )

    assert swallowed_error(discarding) == 1
    assert swallowed_error(discarding, discard="raw") == 1
    assert swallowed_error(throwing) == 0
    assert swallowed_error(throwing, failures_as_values=("python",)) == 1


def test_an_error_replacing_another_arrives_without_it() -> None:
    """The stack that names what actually broke lives on the failure being replaced.

    A raise wrapped by a formatter still states its cause on the line that closes it, and the
    marker differs by language while the defect and the fix do not.
    """
    dropped = DECLARED.of(
        guard(
            "try:\n    profile = read(path)\nexcept OSError as error:\n"
            '    raise ConfigurationError("the profile is unreadable")'
        )
    )
    carried = DECLARED.of(
        guard(
            "try:\n    profile = read(path)\nexcept OSError as error:\n"
            '    raise ConfigurationError("the profile is unreadable") from error'
        )
    )
    wrapped = DECLARED.of(
        guard(
            "try:\n    profile = read(path)\nexcept OSError as error:\n"
            "    raise ConfigurationError(\n"
            '        "the profile is unreadable"\n'
            "    ) from error"
        )
    )
    braced_dropped = DECLARED.of(
        guard(
            "try {\n    deliver(message);\n} catch {\n"
            '    throw new DeliveryError("delivery failed");\n}'
        )
    )
    braced_carried = DECLARED.of(
        guard(
            "try {\n    deliver(message);\n} catch (error) {\n"
            '    throw new DeliveryError("delivery failed", { cause: error });\n}'
        )
    )

    assert raise_without_cause(dropped) == 1
    assert raise_without_cause(carried) == 0
    assert raise_without_cause(dropped, raises=("throw",)) == 0
    assert raise_without_cause(wrapped) == 0
    assert raise_without_cause(braced_dropped) == 1
    assert raise_without_cause(braced_carried) == 0


def test_a_raise_is_judged_on_the_failure_its_own_clause_holds() -> None:
    """The types in `except (OSError, ValueError)` are not a name a raise could carry.

    A handler that decides whether to translate still has to carry what it caught, however deep
    the branch it sits under. Nothing replaces the failure in a bare re-raise, so there is nothing
    for a cause to carry, and a guard stating only cleanup holds no clause where one could drop.
    """
    unnamed = DECLARED.of(
        guard(
            "try:\n    profile = read(path)\nexcept (OSError, ValueError):\n"
            '    raise ConfigurationError("the profile is unreadable")'
        )
    )
    broken_on_purpose = DECLARED.of(
        guard(
            "try:\n    profile = read(path)\nexcept (OSError, ValueError):\n"
            '    raise ConfigurationError("the profile is unreadable") from None'
        )
    )
    branched = DECLARED.of(
        guard(
            "try:\n    profile = read(path)\nexcept OSError as error:\n"
            '    if fatal:\n        raise ConfigurationError("unreadable")\n'
            "    logger.warning(error)"
        )
    )
    re_raised = DECLARED.of(
        guard("try:\n    profile = read(path)\nexcept OSError:\n    close(path)\n    raise")
    )
    cleanup_only = DECLARED.of(
        guard(
            'try:\n    raise ConfigurationError("the profile is unreadable")\n'
            "finally:\n    close(path)"
        )
    )

    assert raise_without_cause(unnamed) == 1
    assert raise_without_cause(broken_on_purpose) == 0
    assert raise_without_cause(broken_on_purpose, causes=("cause",)) == 1
    assert raise_without_cause(branched) == 1
    assert raise_without_cause(re_raised) == 0
    assert raise_without_cause(cleanup_only) == 0


def test_the_base_error_type_leaves_a_caller_nothing_to_single_out() -> None:
    """Catching this one failure means catching every other failure in the same region.

    `builtins.Exception` and a bare `Error` name the same base a caller cannot narrow, while a
    re-raise and a failure already held construct nothing, so neither can name the wrong type.
    """
    subject = DECLARED.of(raised(call("Exception")), raised(call("ConfigurationError")))
    qualified = DECLARED.of(
        raised(call("builtins.Exception")), raised(SyntaxNode(kind="name", name="Error"))
    )
    constructing_nothing = DECLARED.of(raised(), raised(SyntaxNode(kind="name", name="error")))

    assert vanilla_error_type(subject) == 1
    assert vanilla_error_type(subject, base_errors=("ConfigurationError",)) == 1
    assert vanilla_error_type(qualified) == 2
    assert vanilla_error_type(constructing_nothing) == 0


def test_a_guard_that_catches_what_its_own_body_threw() -> None:
    """The raise is a jump to a handler a few lines below rather than a failure to report.

    The check reads the same whether it is written flat or under a condition, and moving it into
    its own function is the fix, so a raise inside a callable the region declares is never the
    finding, just as a guard protecting the calls around it is the arrangement the rule wants.
    """
    subject = DECLARED.of(
        guard(
            "try:\n    record = fetch(key)\n    raise StaleRecord(key)\n"
            "except StaleRecord:\n    record = rebuild(key)",
            raised(call("StaleRecord")),
        )
    )
    protecting_calls = DECLARED.of(
        guard(
            "try:\n    record = fetch(key)\nexcept StaleRecord:\n    record = rebuild(key)",
            SyntaxNode(kind="effect", children=[call("fetch")]),
        )
    )
    under_a_branch = DECLARED.of(
        guard(
            "try:\n    record = fetch(key)\n    if record.expired:\n        raise StaleRecord(key)"
            "\nexcept StaleRecord:\n    record = rebuild(key)",
            SyntaxNode(kind="branch", children=[raised(call("StaleRecord"))]),
        )
    )
    extracted = DECLARED.of(
        guard(
            "try:\n    record = fresh(key)\nexcept StaleRecord:\n    record = rebuild(key)",
            SyntaxNode(kind="callable", name="fresh", children=[raised(call("StaleRecord"))]),
        )
    )

    assert raise_inside_guarded_region(subject) == 1
    assert raise_inside_guarded_region(protecting_calls) == 0
    assert raise_inside_guarded_region(under_a_branch) == 1
    assert raise_inside_guarded_region(extracted) == 0


def test_a_guard_no_clause_of_which_would_catch_the_raise_is_left_alone() -> None:
    """Cleanup that always runs never sees the failure, so it cannot be catching its own.

    A clause naming another type leaves the raise entirely, which is the guard protecting the
    calls around it rather than performing a check on purpose.
    """
    cleanup_only = DECLARED.of(
        guard(
            "try:\n    record = fetch(key)\n    raise StaleRecord(key)\nfinally:\n    close(key)",
            raised(call("StaleRecord")),
        )
    )
    another_type = DECLARED.of(
        guard(
            "try:\n    consume(limits)\n    raise QuotaExceeded(kind)\n"
            "except DatabaseError as error:\n    retry(error)",
            raised(call("QuotaExceeded")),
        )
    )

    assert raise_inside_guarded_region(cleanup_only) == 0
    assert raise_inside_guarded_region(another_type) == 0


def test_a_clause_that_names_no_type_or_a_base_type_catches_whatever_the_body_threw() -> None:
    """A bare handler and a broad one both land on the check the body performed on purpose.

    `catch (StaleRecord error)` names a type where `catch (error)` names only a binding, and both
    braced clauses still catch what the region threw.
    """
    bare = DECLARED.of(
        guard(
            "try:\n    record = fetch(key)\n    raise StaleRecord(key)\n"
            "except:\n    record = None",
            raised(call("StaleRecord")),
        )
    )
    broad = DECLARED.of(
        guard(
            "try:\n    record = fetch(key)\n    raise StaleRecord(key)\n"
            "except Exception:\n    record = None",
            raised(call("StaleRecord")),
        )
    )
    typed = DECLARED.of(
        guard(
            "try {\n    record = fetch(key);\n    throw new StaleRecord(key);\n"
            "} catch (StaleRecord error) {\n    record = rebuild(key);\n}",
            raised(call("StaleRecord")),
        )
    )
    untyped = DECLARED.of(
        guard(
            "try {\n    record = fetch(key);\n    throw new StaleRecord(key);\n"
            "} catch (error) {\n    record = rebuild(key);\n}",
            raised(call("StaleRecord")),
        )
    )

    assert raise_inside_guarded_region(bare) == 1
    assert raise_inside_guarded_region(broad) == 1
    assert raise_inside_guarded_region(broad, catch_all=()) == 0
    assert raise_inside_guarded_region(typed) == 1
    assert raise_inside_guarded_region(untyped) == 1


def test_a_declaration_carrying_no_tree_is_never_judged() -> None:
    """A fact that was never asked to carry a tree cannot answer a question about code."""
    subject = DECLARED.around(None)

    assert swallowed_error(subject) == 0
    assert raise_without_cause(subject) == 0
    assert vanilla_error_type(subject) == 0
    assert raise_inside_guarded_region(subject) == 0


def test_a_type_reaches_its_code_through_the_callables_it_owns() -> None:
    """Judging the type as well would report every defect in its methods a second time."""
    owner = RUSTY.of(
        guard(
            "try:\n    profile = read(path)\nexcept OSError:\n    pass",
            raised(call("Exception")),
        )
    ).model_copy(update={"kind": "type"})

    assert swallowed_error(owner) == 0
    assert raise_without_cause(owner) == 0
    assert vanilla_error_type(owner) == 0
    assert raise_inside_guarded_region(owner) == 0
