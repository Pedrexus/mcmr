use oxc_ast::ast::{ExportSpecifier, ImportDeclarationSpecifier};

pub(in crate::typescript::graph::collector) struct ImportedBinding {
    pub(in crate::typescript::graph::collector) bound: String,
    pub(in crate::typescript::graph::collector) name: String,
}

impl ImportedBinding {
    pub(in crate::typescript::graph::collector) fn from_export(
        specifier: &ExportSpecifier<'_>,
    ) -> Self {
        Self {
            bound: specifier.exported.name().to_string(),
            name: specifier.local.name().to_string(),
        }
    }

    pub(in crate::typescript::graph::collector) fn from_import(
        specifier: &ImportDeclarationSpecifier<'_>,
    ) -> Self {
        match specifier {
            ImportDeclarationSpecifier::ImportSpecifier(held) => Self {
                bound: held.local.name.to_string(),
                name: held.imported.name().to_string(),
            },
            ImportDeclarationSpecifier::ImportDefaultSpecifier(held) => Self {
                bound: held.local.name.to_string(),
                name: "default".to_string(),
            },
            ImportDeclarationSpecifier::ImportNamespaceSpecifier(held) => Self {
                bound: held.local.name.to_string(),
                name: String::new(),
            },
        }
    }
}
