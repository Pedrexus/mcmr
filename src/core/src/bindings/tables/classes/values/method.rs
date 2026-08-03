use crate::classes::MethodRecord;

#[derive(Clone, Copy)]
pub(in crate::bindings::tables::classes) enum MethodValue {
    Decorator,
    OwnerQualifiedCall,
}

impl MethodValue {
    pub(in crate::bindings::tables::classes) fn values(self, method: &MethodRecord) -> &[String] {
        match self {
            Self::Decorator => &method.decorators,
            Self::OwnerQualifiedCall => &method.owner_qualified_calls,
        }
    }
}
