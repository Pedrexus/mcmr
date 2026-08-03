/// One directory the walk met, described by what it holds rather than by what was parsed in it.
///
/// A directory is not a language construct, so nothing here comes from a frontend. Deriving these
/// counts from the files a frontend parsed would make a directory holding no source invisible,
/// and that is precisely the directory a rule about empty directories has to be able to see.
#[derive(Debug, Default)]
pub struct Directory {
    pub relative: String,
    pub entry_count: usize,
    pub direct_file_count: usize,
    pub direct_directory_count: usize,
    pub only_child_directory: Option<String>,
    pub direct_module_count: usize,
}
