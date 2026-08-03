/// One member of a class, read for whether inheriting it twice would be a hazard.
pub(in crate::classes) struct Member {
    pub(in crate::classes) name: String,
    pub(in crate::classes) is_concrete: bool,
    pub(in crate::classes) delegates_to_super: bool,
}
