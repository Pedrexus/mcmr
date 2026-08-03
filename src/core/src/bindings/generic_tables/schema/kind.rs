use serde_json::Value;

#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub(crate) enum ScalarKind {
    Boolean,
    Float,
    Integer,
    String,
}

impl ScalarKind {
    pub(crate) fn of(value: &Value) -> Option<Self> {
        match value {
            Value::Bool(_) => Some(Self::Boolean),
            Value::Number(number) if number.is_i64() || number.is_u64() => Some(Self::Integer),
            Value::Number(_) => Some(Self::Float),
            Value::String(_) => Some(Self::String),
            _ => None,
        }
    }

    pub(crate) fn suffix(self) -> &'static str {
        match self {
            Self::Boolean => "boolean",
            Self::Float => "float",
            Self::Integer => "integer",
            Self::String => "string",
        }
    }
}
