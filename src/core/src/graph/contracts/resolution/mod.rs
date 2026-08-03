use serde::Serialize;

/// How completely one relationship was resolved, which a consumer must be able to see.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Resolution {
    Exact,
    External,
    Unresolved,
}
