use oxc_ast::ast::ImportDeclarationSpecifier;

pub(super) struct ImportedNames {
    pub(super) bound: String,
    pub(super) imported: String,
}

impl ImportedNames {
    pub(super) fn new(specifier: &ImportDeclarationSpecifier<'_>) -> Self {
        let (bound, imported) = match specifier {
            ImportDeclarationSpecifier::ImportSpecifier(named) => (
                named.local.name.to_string(),
                named.imported.name().to_string(),
            ),
            ImportDeclarationSpecifier::ImportDefaultSpecifier(default) => {
                (default.local.name.to_string(), "default".to_string())
            }
            ImportDeclarationSpecifier::ImportNamespaceSpecifier(namespace) => {
                (namespace.local.name.to_string(), "*".to_string())
            }
        };
        Self { bound, imported }
    }
}
