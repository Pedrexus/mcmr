#[derive(Clone, Copy, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub(in crate::typescript::facts::syntax) enum SyntaxSemantic {
    Await,
    Binding,
    Branch,
    Call,
    Callable,
    Collection,
    Effect,
    Guard,
    Literal,
    Loop,
    Member,
    Name,
    Operation,
    Raise,
    Return,
    Scope,
    Text,
    Type,
}
