use super::super::site::Site;
use crate::graph::Language;
use std::collections::BTreeMap;

pub(crate) type WindowIdentity<'a> = (Language, &'a [u32], Vec<u32>);
pub(crate) type WindowGroups<'a> = BTreeMap<WindowIdentity<'a>, Vec<Site>>;
