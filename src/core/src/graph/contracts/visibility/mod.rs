use serde::Serialize;

/// How widely one declaration reaches, in the one vocabulary every frontend fills.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Visibility {
    Public,
    Protected,
    Internal,
    Private,
}

impl Visibility {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Public => "public",
            Self::Protected => "protected",
            Self::Internal => "internal",
            Self::Private => "private",
        }
    }
}
