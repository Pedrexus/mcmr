use crate::discovery;

#[derive(Clone, Copy)]
pub(crate) struct DocumentExtraction<'a> {
    pub(crate) documents: &'a [discovery::Document],
    pub(crate) packages: &'a discovery::Packages,
    pub(crate) families: &'a [String],
}
