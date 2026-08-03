use serde::Serialize;

#[derive(Clone, Debug, Default, Serialize)]
pub struct FunctionRoles {
    pub has_tensor_shape_semantics: bool,
    pub has_tensor_dtype_semantics: bool,
    pub is_protocol_name: bool,
    pub is_async: bool,
    pub is_recursive: bool,
    pub is_first_class_reference: bool,
    pub is_abstract: bool,
}
