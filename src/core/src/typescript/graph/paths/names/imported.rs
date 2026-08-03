#[derive(Clone, Copy)]
pub(in crate::typescript::graph) struct ImportedName<'name> {
    pub(in crate::typescript::graph) module: &'name str,
    pub(in crate::typescript::graph) member: &'name str,
}

impl ImportedName<'_> {
    pub(in crate::typescript::graph) fn render(&self) -> String {
        format!("{}.{}", self.module, self.member)
    }
}
