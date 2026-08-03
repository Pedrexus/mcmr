use serde::Serialize;

/// How one parameter binds an argument.
///
/// Python spells all five forms. Other frontends choose the exact form their grammar provides,
/// which lets signature comparison distinguish positional and named compatibility.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ParameterKind {
    PositionalOnly,
    PositionalOrKeyword,
    KeywordOnly,
    VarPositional,
    VarKeyword,
}
