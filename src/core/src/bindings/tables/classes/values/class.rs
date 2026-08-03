use crate::classes::ClassAnalysisRecord;

#[derive(Clone, Copy)]
pub(in crate::bindings::tables::classes) enum ClassValue {
    DirectBase,
    Decorator,
    Keyword,
    DirectSubclass,
    ImportingModule,
}

impl ClassValue {
    pub(in crate::bindings::tables::classes) fn values(
        self,
        class: &ClassAnalysisRecord,
    ) -> &[String] {
        match self {
            Self::DirectBase => &class.declaration.direct_bases,
            Self::Decorator => &class.declaration.decorators,
            Self::Keyword => &class.declaration.class_keywords,
            Self::DirectSubclass => &class.shape.direct_subclasses,
            Self::ImportingModule => &class.model.importing_modules,
        }
    }
}
