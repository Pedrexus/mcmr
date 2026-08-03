from pathlib import Path

from mcmr.rules.general import (
    raise_without_cause,
    swallowed_error,
    vanilla_error_type,
)

from .support import query, table, value


def test_a_handler_that_answers_with_nothing_throws_the_failure_away(tmp_path: Path) -> None:
    """Empty, inert, and comment-only handlers discard failures across languages."""
    subject = table(
        tmp_path,
        {
            "python_cases.py": """def dropped(queue):
    try:
        deliver()
    except TimeoutError:
        pass
    for message in queue:
        try:
            deliver(message)
        except TimeoutError:
            continue


def answered(queue):
    try:
        deliver()
    except TimeoutError as error:
        logger.warning(error)
        queue.retry()
""",
            "typescript_cases.ts": """function inline() {
  try {
    deliver();
  } catch (error) {
  }
}
""",
            "cpp_cases.cpp": """void allman() {
    try
    {
        deliver();
    }
    catch (const Timeout& error)
    {
    }
}

void braced_answer() {
    try { deliver(); } catch (const Timeout& error) { log(error); }
}

void excused() {
    try {
        deliver();
    } catch (const Timeout& error) {
        // nothing to do here
    }
}
""",
        },
    )
    default = query(swallowed_error, subject)
    pass_only = query(swallowed_error, subject, inert=["pass"])

    assert value(default, subject, "dropped") == 2
    assert value(pass_only, subject, "dropped") == 1
    assert value(default, subject, "answered") == 0
    assert value(default, subject, "inline") == 1
    assert value(default, subject, "allman") == 1
    assert value(default, subject, "braced_answer") == 0
    assert value(default, subject, "excused") == 1


def test_a_result_bound_to_the_throwaway_name_is_discarded_too(tmp_path: Path) -> None:
    """Only fallible calls discarded in configured result languages count."""
    subject = table(
        tmp_path,
        {
            "discard.rs": """fn discarding(path: &str, anchor: &str) {
    let _ = deliver();
    let raw = deliver();
    let _ = 3;
    let Some((_, inside)) = path.split_once(anchor);
}
""",
            "discard.py": "def throwing():\n    _ = deliver()\n",
        },
    )
    default = query(swallowed_error, subject)
    raw = query(swallowed_error, subject, discard="raw")
    python_values = query(swallowed_error, subject, failures_as_values=["python"])

    assert value(default, subject, "discarding") == 1
    assert value(raw, subject, "discarding") == 1
    assert value(default, subject, "throwing") == 0
    assert value(python_values, subject, "throwing") == 1


def test_an_error_replacing_another_arrives_without_it(tmp_path: Path) -> None:
    """Replacement errors retain the caught failure through each language's cause syntax."""
    subject = table(
        tmp_path,
        {
            "cause.py": """def dropped(path):
    try:
        read(path)
    except OSError as error:
        raise ConfigurationError("unreadable")


def carried(path):
    try:
        read(path)
    except OSError as error:
        raise ConfigurationError("unreadable") from error


def wrapped(path):
    try:
        read(path)
    except OSError as error:
        raise ConfigurationError(
            "unreadable"
        ) from error
""",
            "cause.ts": """function braced_dropped() {
  try {
    deliver();
  } catch (error) {
    throw new DeliveryError("failed");
  }
}

function braced_carried() {
  try {
    deliver();
  } catch (error) {
    throw new DeliveryError("failed", { cause: error });
  }
}
""",
        },
    )
    default = query(raise_without_cause, subject)
    throw_only = query(raise_without_cause, subject, raises=["throw"])

    assert value(default, subject, "dropped") == 1
    assert value(default, subject, "carried") == 0
    assert value(throw_only, subject, "dropped") == 0
    assert value(default, subject, "wrapped") == 0
    assert value(default, subject, "braced_dropped") == 1
    assert value(default, subject, "braced_carried") == 0


def test_a_raise_is_judged_on_the_failure_its_own_clause_holds(tmp_path: Path) -> None:
    """Branches, bare reraises, and cleanup regions retain their original cause semantics."""
    subject = table(
        tmp_path,
        {
            "cause_shapes.py": """def unnamed(path):
    try:
        read(path)
    except (OSError, ValueError):
        raise ConfigurationError("unreadable")


def broken_on_purpose(path):
    try:
        read(path)
    except (OSError, ValueError):
        raise ConfigurationError("unreadable") from None


def branched(path, fatal):
    try:
        read(path)
    except OSError as error:
        if fatal:
            raise ConfigurationError("unreadable")
        logger.warning(error)


def re_raised(path):
    try:
        read(path)
    except OSError:
        close(path)
        raise


def cleanup_only(path):
    try:
        raise ConfigurationError("unreadable")
    finally:
        close(path)
"""
        },
    )
    default = query(raise_without_cause, subject)
    cause_only = query(raise_without_cause, subject, causes=["cause"])

    assert value(default, subject, "unnamed") == 1
    assert value(default, subject, "broken_on_purpose") == 0
    assert value(cause_only, subject, "broken_on_purpose") == 1
    assert value(default, subject, "branched") == 1
    assert value(default, subject, "re_raised") == 0
    assert value(default, subject, "cleanup_only") == 0


def test_the_base_error_type_leaves_a_caller_nothing_to_single_out(tmp_path: Path) -> None:
    """Base errors are reported while named errors, reraises, and held values are not."""
    subject = table(
        tmp_path,
        {
            "vanilla.py": """def subject():
    raise Exception()
    raise ConfigurationError()


def qualified():
    raise builtins.Exception()
    raise Error


def constructing_nothing(error):
    raise
    raise error
"""
        },
    )
    default = query(vanilla_error_type, subject)
    configured = query(vanilla_error_type, subject, base_errors=["ConfigurationError"])

    assert value(default, subject, "subject") == 1
    assert value(configured, subject, "subject") == 1
    assert value(default, subject, "qualified") == 2
    assert value(default, subject, "constructing_nothing") == 0
