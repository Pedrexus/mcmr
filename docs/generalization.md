# Language generalization

MCMR splits rules into a `general` scope that any provider can answer and a `python` scope that
depends on one language. A rule belongs in `general` when its evidence exists in every language a
provider might implement, even when each language spells that evidence differently. The provider
resolves the spelling; the rule reasons over the resolved form.

## Shared vocabulary

Three enums carry the concepts that let object-language rules generalize.

`Visibility` names how widely a declaration reaches: `public`, `protected`, `internal`, `private`.
Each provider maps its own language onto it.

| Language | public | protected | internal | private |
| --- | --- | --- | --- | --- |
| Python | `name` | `_name` in a class | `_name` at module scope | `__name` |
| Java, C# | `public` | `protected` | package private, `internal` | `private` |
| Kotlin | `public` | `protected` | `internal` | `private` |
| Rust | `pub` | — | `pub(crate)`, `pub(super)` | no qualifier |
| Go | capitalized | — | lowercase, `internal/` package | — |
| TypeScript | `export` | `protected` | module local | `private`, `#field` |
| C++ | `public` | `protected` | anonymous namespace | `private` |

A language protocol name is not a visibility. A Python dunder, a Rust trait method, and a C#
operator are marked `is_protocol_name` so a rule can order or exempt them without matching spelling.

`MemberKind` names what a declared member is: `constructor`, `property`, `static_method`,
`class_method`, `method`, `field`. `ReceiverKind` names whose member an access reads: `self`,
`owner`, `super`, `other`.

## Rules generalized

* **`ALL-CLAS0001` class method order**, was `PY-CLAS0002`. The Python-shaped `category_order`
  tuple of fourteen strings became two orthogonal settings, `visibility_order` and `kind_order`,
  with lifecycle names first and protocol members second. Any language that declares members inside
  a type now sorts under one policy.
* **`ALL-CLAS0002` nonpublic top level class count** was retired. Module-local classes are exactly
  what a narrow public surface needs, so forbidding them contradicted `ALL-REAC0002`.
* **`ALL-ENCA0001` external nonpublic attribute access**, was `PY-ENCA0001`. Underscore matching and
  the `self`, `cls`, `current_class` receiver strings became `Visibility` and `ReceiverKind`. This
  is the classic encapsulation break in Java, C#, C++, and TypeScript alike.
* **`ALL-PARA0004` boolean parameter count**, replacing `PY-FUNC0007`. The narrow rule matched a
  Python annotation and a Python default cluster; the general one counts a flag wherever a caller
  passes it, which is one design decision spelled the same way in Rust, TypeScript, and C++.

## Ranked candidates

These stay in the Python scope today. Each is generalizable once its fact carries the resolved form
instead of Python spelling, in roughly descending order of value.

1. **`PY-IMPO0002` project private import.** Crossing a nonpublic boundary is enforced by Go's
   `internal/` packages, Rust's `pub(crate)`, and Java's package privacy. Needs `Visibility` on the
   imported binding.
2. **`PY-IMPO0003` unused import.** Every language with imports has it. Already visibility-free.
3. **`PY-DEAD0001` unreferenced private function.** An unused private declaration is dead code
   anywhere. Needs `Visibility` on `FunctionFact`, which now exists.
4. **`PY-LOGG0001` logger boundary bypass.** `print`, `console.log`, `System.out`, `println!` are the
   same bypass. The preferred logger is already a setting.
5. **`PY-INTE0001` concrete isinstance capability.** Testing a concrete type instead of the
   capability is the classic `instanceof` smell in Java and C#.
6. ~~**`PY-FUNC0007` positional configuration parameter.**~~ Retired. The Boolean trap is
   language-neutral and now lands as `ALL-PARA0003` for a flag a caller cannot name and
   `ALL-PARA0004` for the state space every flag adds, whichever way it is passed.
7. **`PY-CLAS0003` utility namespace class.** A class of only static members is a namespace in Java,
   C#, and TypeScript too.
8. **`PY-CLAS0005`, `PY-CLAS0006` speculative base and pass-through layer.** Inheritance smells that
   need no Python specifics, once their verdict fields become graph evidence.
9. **`PY-EXCE0001`, `PY-EXCE0002`, `PY-EXCE0003` exception region rules.** Protected regions exist in
   every language with exceptions.
10. **`PY-TYPE0004` prohibited annotation.** The escape hatch type is `Any`, `any`, `interface{}`,
    or `Object` depending on the language, and the list is already a setting.
11. **`PY-TEST0008`, `PY-TEST0011`, `PY-TEST0012`, `PY-TEST0013` test shape rules.** Shared test
    state, branching tests, oversized tests, and hand-rolled case loops are the same smells in
    JUnit, Go table tests, and Jest.

Rules that stay language-scoped are the ones whose evidence is the language itself: comprehensions,
decorators and caching, positional-only parameters, `__future__` imports, and the Python typing
surface.

## Framework rules are not language rules

Sixteen rules cover SQLAlchemy, SQLModel, Pydantic, and Torch. They live under `python` because that
is the only scope available, but they are about a library rather than a language. A third axis, an
ecosystem a project either uses or does not, would let those rules be selected by fact rather than
by language, and would keep the Python scope about Python. This is a phase two decision, since it
changes rule identity.
