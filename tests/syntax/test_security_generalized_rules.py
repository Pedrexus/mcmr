from typing import TYPE_CHECKING, cast

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import SyntaxFact
from mcmr.query import RuleQuery, scalar_row_value
from mcmr.rules.general import (
    command_built_from_a_shell_string,
    credential_written_into_source,
    unseeded_randomness_for_secrets,
    weak_hashing_primitive,
)
from mcmr.table import AnalysisSession, SyntaxRelation

from ..support import written

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from mcmr.plugins import Table


def table(root: Path, sources: Mapping[str, str]) -> Table[SyntaxFact]:
    """Parse one security corpus into specialized syntax relations."""
    return AnalysisSession(
        written(root, dict(sources)),
        suffixes=[".py"],
        typed_families=[SyntaxFact],
    ).syntax_tables()


def query(
    rule: RuleContract,
    subject: Table[SyntaxFact],
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one security rule once over every declaration."""
    result = rule.invoke_table(
        subject,
        settings=settings,
        dependencies={},
    )
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic security rule returned a model query")
    return result


def values(
    rule: RuleContract,
    subject: Table[SyntaxFact],
    **settings: RuleSetting,
) -> dict[str, RuleValue]:
    """Return every declaration value from one repository-wide rule query."""
    facts = subject.frame(SyntaxRelation.FACTS).select("fact_id", "qualname")
    rows = query(rule, subject, **settings).values.collect().join(facts, on="fact_id")
    return {
        cast("str", row["qualname"]): scalar_row_value(row) for row in rows.iter_rows(named=True)
    }


def test_a_broken_hash_is_reported_however_a_language_spells_it(tmp_path: Path) -> None:
    """Broken primitives count by callee and factory arguments across spellings."""
    subject = table(
        tmp_path,
        {
            "hashes.py": """
def issue(payload):
    signature = hashlib.md5(payload)
    legacy = crypto.createHash("MD5")
    modern = hashlib.sha256(payload)
    label = record("md5")

def cache_key(path):
    bucket = hashlib.md5(path, usedforsecurity=False)

def house(payload):
    signature = crypto.weakdigest(payload)
"""
        },
    )

    default = values(weak_hashing_primitive, subject)
    extended = values(weak_hashing_primitive, subject, also_broken=["weakdigest"])

    assert default["issue"] == 2
    assert default["cache_key"] == 0
    assert default["house"] == 0
    assert extended["house"] == 1


def test_a_token_drawn_from_an_ordinary_generator_is_reported(tmp_path: Path) -> None:
    """Only predictable draws bound beneath names that promise secrecy count."""
    subject = table(
        tmp_path,
        {
            "tokens.py": """
def issue():
    session_token = Math.random()
    retry_delay = random.uniform(0.1, 0.5)

def from_the_system(alphabet):
    session_token = secrets.token_hex(32)
    api_key = secrets.choice(alphabet)

def map_key(names):
    key = random.choice(names)

def house(alphabet):
    api_key = house.pick(alphabet)
"""
        },
    )

    default = values(unseeded_randomness_for_secrets, subject)
    extended = values(
        unseeded_randomness_for_secrets,
        subject,
        also_predictable=["pick"],
    )

    assert default["issue"] == 1
    assert default["from_the_system"] == 0
    assert default["map_key"] == 0
    assert default["house"] == 0
    assert extended["house"] == 1


def test_a_credential_written_beside_a_secret_name_is_reported(tmp_path: Path) -> None:
    """Credential literals count while placeholders and location names remain exempt."""
    subject = table(
        tmp_path,
        {
            "credentials.py": """
def issue():
    password = "hunter2"
    secret = os.getenv("APP_SECRET")
    greeting = "hello"

def defaulted(host, password="hunter2"):
    return host

def templates():
    password = "changeme"
    api_key = "<your-api-key>"
    token = ""

def locations():
    password_file = "/etc/app/db.pass"
    key = "user_id"
    foreign_key = f"{remote.table.fullname}.{remote.name}"
    primary_key = "account_id"

def house():
    pin = "4821"
"""
        },
    )

    default = values(credential_written_into_source, subject)
    extended = values(credential_written_into_source, subject, also_secret=["pin"])

    assert default["issue"] == 1
    assert default["defaulted"] == 1
    assert default["templates"] == 0
    assert default["locations"] == 0
    assert default["house"] == 0
    assert extended["house"] == 1


def test_a_command_line_handed_to_a_shell_is_reported(tmp_path: Path) -> None:
    """Shell launches count while structured and explicitly refused launches stay safe."""
    subject = table(
        tmp_path,
        {
            "commands.py": """
def issue(path, command, name):
    cleanup = os.system("rm -rf " + path)
    status = subprocess.run(command, shell=True)
    listing = child_process.exec("ls " + name)
    example = call("shell=True")

def house(command):
    output = house.run_in_shell(command)

def bare(path):
    code = system("rm -rf " + path)

def probes():
    name = platform.system()
    release = platform.uname()

def combined(run):
    measured = state.exec(exec_tag.sync | exec_tag.timer, run)

def separated(ref, statement):
    checkout = subprocess.run(["git", "checkout", ref])
    rows = session.exec(statement)
    started = time.time()

def refused(ref):
    status = subprocess.run("git " + ref, shell=False)
"""
        },
    )

    default = values(command_built_from_a_shell_string, subject)
    extended = values(
        command_built_from_a_shell_string,
        subject,
        also_through_a_shell=["run_in_shell"],
    )

    assert default == {
        "issue": 3,
        "house": 0,
        "bare": 1,
        "probes": 0,
        "combined": 0,
        "separated": 0,
        "refused": 0,
    }
    assert extended["house"] == 1


def test_an_empty_declaration_is_never_judged(tmp_path: Path) -> None:
    """A declaration without relevant syntax receives the neutral value from every rule."""
    subject = table(
        tmp_path,
        {"empty.py": "def empty():\n    pass\n"},
    )

    assert values(weak_hashing_primitive, subject)["empty"] == 0
    assert values(unseeded_randomness_for_secrets, subject)["empty"] == 0
    assert values(credential_written_into_source, subject)["empty"] == 0
    assert values(command_built_from_a_shell_string, subject)["empty"] == 0
