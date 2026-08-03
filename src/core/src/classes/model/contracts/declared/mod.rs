use crate::protocol::Span as SourceSpan;

mod member;
mod shape;

pub(in crate::classes) use member::Member;
pub(in crate::classes) use shape::ClassShape;

/// One top-level class exactly as the file declaring it writes it down.
pub(in crate::classes) struct Declared {
    pub(in crate::classes) name: String,
    pub(in crate::classes) span: SourceSpan,
    pub(in crate::classes) bases: Vec<String>,
    pub(in crate::classes) line_count: usize,
    pub(in crate::classes) members: Vec<Member>,
    pub(in crate::classes) field_count: usize,
    pub(in crate::classes) shape: ClassShape,
}
