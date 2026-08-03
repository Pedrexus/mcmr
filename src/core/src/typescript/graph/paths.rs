#[cfg(test)]
pub(in crate::typescript) use configuration::mappings_at;
pub use configuration::{Specifiers, WrittenSpecifier};
#[cfg(test)]
pub(in crate::typescript) use json::parse_config;
pub use support::Located;
pub(super) use support::split_import;

mod configuration;
mod json;
pub(super) mod names;
pub(super) mod support;
