use tree_sitter::Node as Syntax;

pub(crate) fn is_type(node: Syntax) -> bool {
    matches!(
        node.kind(),
        "class_specifier" | "struct_specifier" | "union_specifier" | "enum_specifier"
    )
}

pub(crate) fn is_name(node: Syntax) -> bool {
    matches!(
        node.kind(),
        "identifier"
            | "field_identifier"
            | "type_identifier"
            | "qualified_identifier"
            | "destructor_name"
            | "operator_name"
    )
}
