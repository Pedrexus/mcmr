mod attachment;
mod context;
mod resolver;

pub(crate) use attachment::Attachment;
pub(crate) use context::ResolutionContext;
pub(crate) use resolver::{attach, is_builtin, resolve};
pub use resolver::{expand, stray};
