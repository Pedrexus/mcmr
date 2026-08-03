pub(in crate::typescript::graph) struct JoinedPath<'path> {
    pub(in crate::typescript::graph) parent: &'path str,
    pub(in crate::typescript::graph) child: &'path str,
}

impl JoinedPath<'_> {
    pub(in crate::typescript::graph) fn normalized(&self) -> String {
        super::super::support::normalized(&self.render())
    }

    pub(in crate::typescript::graph) fn render(&self) -> String {
        if self.parent.is_empty() {
            return self.child.to_owned();
        }
        format!("{}/{}", self.parent, self.child)
    }
}
