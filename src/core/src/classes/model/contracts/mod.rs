mod declared;
mod stated;

pub(in crate::classes) use declared::{ClassShape, Declared, Member};
pub(in crate::classes) use stated::{ModuleShape, ModuleUsage, Stated};

/// One class, named the way the whole repository names it.
pub(in crate::classes) type Identity = (String, String);
