#[derive(Clone, Debug)]
pub(crate) enum ScalarValue {
    Boolean(bool),
    Float(f64),
    Integer(i64),
    String(String),
}

macro_rules! copied_scalar {
    ($name:ident, $variant:ident, $kind:ty) => {
        pub(crate) fn $name(&self) -> Option<$kind> {
            match self {
                Self::$variant(value) => Some(*value),
                _ => None,
            }
        }
    };
}

impl ScalarValue {
    copied_scalar!(boolean, Boolean, bool);
    copied_scalar!(float, Float, f64);
    copied_scalar!(integer, Integer, i64);

    pub(crate) fn text(&self) -> Option<&str> {
        match self {
            Self::String(value) => Some(value),
            _ => None,
        }
    }
}
