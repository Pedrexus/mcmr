pub(in crate::typescript::facts::syntax) struct QualifiedName<'a> {
    pub(in crate::typescript::facts::syntax) name: &'a str,
    pub(in crate::typescript::facts::syntax) owner: &'a str,
}

impl QualifiedName<'_> {
    pub(in crate::typescript::facts::syntax) fn leaf(&self) -> &str {
        self.name
    }

    pub(in crate::typescript::facts::syntax) fn value(&self) -> String {
        match self.owner.is_empty() {
            true => self.name.to_string(),
            false => format!("{}.{}", self.owner, self.name),
        }
    }
}
