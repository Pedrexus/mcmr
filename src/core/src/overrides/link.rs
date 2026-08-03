use super::contracts::declaration::Declaration;
use crate::graph::Node;

pub(super) struct OverrideLink<'a> {
    pub(super) derived: &'a Node,
    pub(super) base: &'a Node,
    pub(super) depth: usize,
    pub(super) declared: &'a [Declaration],
    pub(super) inherited: &'a [Declaration],
}
