use super::declared::Declared;

mod shape;
mod usage;

pub(in crate::classes) use shape::ModuleShape;
pub(in crate::classes) use usage::ModuleUsage;

/// What one module states about the classes it declares and the names it reaches.
pub(in crate::classes) struct Stated {
    pub(in crate::classes) module: String,
    pub(in crate::classes) path: String,
    pub(in crate::classes) shape: ModuleShape,
    pub(in crate::classes) declared: Vec<Declared>,
    pub(in crate::classes) imported: Vec<(String, String)>,
    pub(in crate::classes) usage: ModuleUsage,
}
