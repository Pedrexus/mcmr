use super::site::Site;

mod contracts;
mod windows;

pub(super) use windows::identical;

pub(super) struct FingerprintBlock<'a> {
    pub(super) index: &'a [(u64, Site)],
    pub(super) block: &'a [(u64, Site)],
}
