pub(crate) const BINDING_DECORATORS: &[&str] = &[
    "abstractmethod",
    "abstractproperty",
    "cache",
    "cached_property",
    "classmethod",
    "deleter",
    "final",
    "getter",
    "lru_cache",
    "override",
    "overload",
    "property",
    "setter",
    "staticmethod",
];

pub(crate) const LIFECYCLE_NAMES: &[&str] = &[
    "__init_subclass__",
    "__post_init__",
    "model_post_init",
    "setUp",
    "setUpClass",
    "setup_method",
    "tearDown",
    "tearDownClass",
    "teardown_method",
];

pub(crate) const MODEL_FOUNDATIONS: &[&str] = &[
    "BaseModel",
    "Component",
    "FlexModel",
    "FrozenFlexModel",
    "FrozenModel",
    "Model",
    "RootModel",
    "SQLModel",
];

pub(crate) const VALIDATION_EXCEPTIONS: &[&str] = &[
    "PydanticCustomError",
    "TypeError",
    "ValidationError",
    "ValueError",
];

pub(crate) const VALIDATOR_DECORATORS: &[&str] = &[
    "field_validator",
    "model_validator",
    "root_validator",
    "validator",
];

pub(crate) const TENSOR_TYPES: &[&str] = &["Array", "DeviceArray", "NDArray", "Tensor", "ndarray"];

pub(crate) const TENSOR_ANNOTATIONS: &[&str] = &[
    "BFloat16",
    "Bool",
    "Complex",
    "Complex64",
    "Complex128",
    "Float",
    "Float16",
    "Float32",
    "Float64",
    "Inexact",
    "Int",
    "Int16",
    "Int32",
    "Int64",
    "Int8",
    "Integer",
    "Key",
    "Num",
    "Real",
    "Shaped",
    "UInt8",
];

pub(crate) const DTYPE_WORDS: &[&str] = &[
    "bfloat16",
    "complex128",
    "complex64",
    "dtype",
    "float16",
    "float32",
    "float64",
    "int16",
    "int32",
    "int64",
    "int8",
    "uint8",
];

pub(crate) fn decorator_name(text: &str) -> &str {
    let applied = text.split('(').next().unwrap_or(text).trim();
    applied.rsplit('.').next().unwrap_or(applied)
}

pub(crate) fn base_name(text: &str) -> &str {
    let named = text
        .split(['[', '('])
        .next()
        .unwrap_or(text)
        .trim()
        .trim_end_matches('.');
    named.rsplit('.').next().unwrap_or(named)
}

pub(crate) fn root_name(expression: &Expr) -> &str {
    match expression {
        Expr::Name(name) => name.id.as_str(),
        Expr::Attribute(item) => root_name(&item.value),
        Expr::Subscript(item) => root_name(&item.value),
        Expr::Call(item) => root_name(&item.func),
        Expr::Starred(item) => root_name(&item.value),
        Expr::Await(item) => root_name(&item.value),
        _ => "",
    }
}

pub(crate) trait PythonName {
    fn visibility_in(&self, scope: &str) -> &'static str;
}

impl PythonName for str {
    fn visibility_in(&self, scope: &str) -> &'static str {
        if is_protocol_name(self) {
            return "public";
        }
        if self.starts_with("__") {
            return "private";
        }
        if self.starts_with('_') {
            return if scope == "method" {
                "protected"
            } else {
                "internal"
            };
        }
        "public"
    }
}

pub(crate) fn is_protocol_name(name: &str) -> bool {
    name.starts_with("__") && name.ends_with("__")
}
use ruff_python_ast::Expr;
