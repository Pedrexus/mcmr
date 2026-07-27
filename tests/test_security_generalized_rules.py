from mcmr.facts import SyntaxNode
from mcmr.rules.general.deterministic.security.r0007 import weak_hashing_primitive
from mcmr.rules.general.deterministic.security.r0008 import unseeded_randomness_for_secrets
from mcmr.rules.general.deterministic.security.r0009 import credential_written_into_source
from mcmr.rules.general.deterministic.security.r0010 import command_built_from_a_shell_string
from tests.conftest import Declaration

DECLARED = Declaration(
    path="src/session.py", qualname="issue", source="def issue(request):\n    ...\n"
)


def literal(written: str) -> SyntaxNode:
    """Build one text node whose text is the literal exactly as the source writes it."""
    return SyntaxNode(kind="text", text=written)


def named(name: str) -> SyntaxNode:
    """Build one name node standing for a value the source reads from somewhere else."""
    return SyntaxNode(kind="name", name=name, text=name)


def built(literal: str, name: str) -> SyntaxNode:
    """Build one operation node standing for a command line the source assembles from parts.

    The pieces are children rather than only text, because that is what a frontend produces and it
    is what tells a command line apart from two values an operator happens to combine.
    """
    return SyntaxNode(
        kind="operation",
        text=f"{literal} + {name}",
        children=[
            SyntaxNode(kind="text", text=literal),
            SyntaxNode(kind="name", name=name, text=name),
        ],
    )


def combined(left: str, right: str) -> SyntaxNode:
    """Build one operation node combining two values, which states no command at all."""
    return SyntaxNode(
        kind="operation",
        text=f"{left} | {right}",
        children=[
            SyntaxNode(kind="name", name=left, text=left),
            SyntaxNode(kind="name", name=right, text=right),
        ],
    )


def call(callee: str, *arguments: SyntaxNode, text: str = "") -> SyntaxNode:
    """Build one call node with its callee first and its arguments after, as a frontend does."""
    receiver = SyntaxNode(kind="member", name=callee.rsplit(".", 1)[-1], text=callee)
    written = text or f"{callee}({', '.join(argument.text for argument in arguments)})"
    return SyntaxNode(kind="call", name=callee, text=written, children=[receiver, *arguments])


def binding(name: str, *values: SyntaxNode, text: str = "") -> SyntaxNode:
    """Build one binding node holding the values its right hand side writes."""
    written = text or f"{name} = {' '.join(value.text for value in values)}"
    return SyntaxNode(kind="binding", name=name, text=written, children=list(values))


def test_a_broken_hash_is_reported_however_a_language_spells_it() -> None:
    """A collision lets someone swap the content behind a signature that still verifies.

    A cache key costs nothing when it collides, so a stated non-security use is honoured, and no
    list of spellings is ever finished, which is why a project extends the one it matches.
    """
    subject = DECLARED.of(
        binding("signature", call("hashlib.md5", named("payload"))),
        binding("legacy", call("crypto.createHash", literal('"MD5"'))),
        binding("modern", call("hashlib.sha256", named("payload"))),
    )
    cache_key = DECLARED.of(
        binding(
            "bucket",
            call("hashlib.md5", named("path"), text="hashlib.md5(path, usedforsecurity=False)"),
        )
    )
    house = DECLARED.of(binding("signature", call("crypto.weakdigest", named("payload"))))

    assert weak_hashing_primitive(subject) == 2
    assert weak_hashing_primitive(cache_key) == 0
    assert weak_hashing_primitive(house) == 0
    assert weak_hashing_primitive(house, also_broken=("weakdigest",)) == 1


def test_a_token_drawn_from_an_ordinary_generator_is_reported() -> None:
    """An observer recovers the sequence from a handful of outputs and mints the next token.

    `secrets` draws from the operating system, so it stays welcome under a secret name, and one
    unqualified word is a map key far more often than a credential.
    """
    subject = DECLARED.of(
        binding("session_token", call("Math.random")),
        binding("retry_delay", call("random.uniform", literal("0.1"), literal("0.5"))),
    )
    from_the_system = DECLARED.of(
        binding("session_token", call("secrets.token_hex", literal("32"))),
        binding("api_key", call("secrets.choice", named("alphabet"))),
    )
    map_key = DECLARED.of(binding("key", call("random.choice", named("names"))))

    assert unseeded_randomness_for_secrets(subject) == 1
    assert unseeded_randomness_for_secrets(from_the_system) == 0
    assert unseeded_randomness_for_secrets(map_key) == 0


def test_a_house_wrapper_around_an_ordinary_generator_is_named_by_the_setting() -> None:
    """A project that hides `random` behind its own name still wants the finding."""
    subject = DECLARED.of(binding("api_key", call("house.pick", named("alphabet"))))

    assert unseeded_randomness_for_secrets(subject) == 0
    assert unseeded_randomness_for_secrets(subject, also_predictable=("pick",)) == 1


def test_a_credential_written_beside_a_secret_name_is_reported() -> None:
    """The value keeps working long after the commit that leaked it is forgotten.

    A default written into a signature ships in the repository exactly as an assignment does.
    """
    subject = DECLARED.of(
        binding("password", literal('"hunter2"')),
        binding("secret", call("os.getenv", literal('"APP_SECRET"'))),
        binding("greeting", literal('"hello"')),
    )
    defaulted = DECLARED.model_copy(
        update={"source": 'def connect(host, password="hunter2"):\n    ...\n'}
    ).of()

    assert credential_written_into_source(subject) == 1
    assert credential_written_into_source(defaulted) == 1


def test_a_template_a_reader_replaces_is_not_a_credential() -> None:
    """An empty value and a placeholder are instructions rather than secrets.

    `password_file` names a path and a bare `key` names a lookup, while every house has a word for
    a secret that no shared list carries and names it through the setting.
    """
    templates = DECLARED.of(
        binding("password", literal('"changeme"')),
        binding("api_key", literal('"<your-api-key>"')),
        binding("token", literal('""')),
    )
    locations = DECLARED.of(
        binding("password_file", literal('"/etc/app/db.pass"')),
        binding("key", literal('"user_id"')),
    )
    house = DECLARED.of(binding("pin", literal('"4821"')))

    assert credential_written_into_source(templates) == 0
    assert credential_written_into_source(locations) == 0
    assert credential_written_into_source(house) == 0
    assert credential_written_into_source(house, also_secret=("pin",)) == 1


def test_a_command_line_handed_to_a_shell_is_reported() -> None:
    """Any value that reaches the string can append a command the caller never wrote.

    A project that hides the shell behind its own helper still wants the finding.
    """
    subject = DECLARED.of(
        binding("cleanup", call("os.system", built("'rm -rf '", "path"))),
        binding(
            "status",
            call("subprocess.run", named("command"), text="subprocess.run(command, shell=True)"),
        ),
        binding("listing", call("child_process.exec", built("'ls '", "name"))),
    )
    house = DECLARED.of(binding("output", call("house.run_in_shell", named("command"))))

    assert command_built_from_a_shell_string(subject) == 3
    assert command_built_from_a_shell_string(house) == 0
    assert command_built_from_a_shell_string(house, also_through_a_shell=("run_in_shell",)) == 1


def test_two_values_an_operator_combines_are_not_a_command_line() -> None:
    """A benchmark handing a launcher two enumerators states no command anybody can reach.

    `state.exec(exec_tag::sync | exec_tag::timer, run)` reads as a launcher taking an assembled
    string wherever an operator alone is taken to mean assembly, which reported a CUDA benchmark
    as shell injection. A list keeps every argument separate no matter what it holds, and saying
    no to a shell is the repair, so the rule reads the refusal too.
    """
    subject = DECLARED.of(
        binding(
            "measured",
            call("state.exec", combined("exec_tag::sync", "exec_tag::timer"), named("run")),
        )
    )
    separated = DECLARED.of(
        binding(
            "checkout",
            call(
                "subprocess.run",
                SyntaxNode(kind="collection", text='["git", "checkout", ref]'),
            ),
        ),
        binding("rows", call("session.exec", named("statement"))),
        binding("started", call("time.time")),
    )
    refused = DECLARED.of(
        binding(
            "status",
            call(
                "subprocess.run",
                built("'git '", "ref"),
                text="subprocess.run('git ' + ref, shell=False)",
            ),
        )
    )

    assert command_built_from_a_shell_string(subject) == 0
    assert command_built_from_a_shell_string(separated) == 0
    assert command_built_from_a_shell_string(refused) == 0


def test_a_declaration_carrying_no_tree_is_never_judged() -> None:
    """A fact carrying no tree was never asked to carry one, whichever rule reads it."""
    subject = DECLARED.around(None)

    assert weak_hashing_primitive(subject) == 0
    assert unseeded_randomness_for_secrets(subject) == 0
    assert credential_written_into_source(subject) == 0
    assert command_built_from_a_shell_string(subject) == 0
