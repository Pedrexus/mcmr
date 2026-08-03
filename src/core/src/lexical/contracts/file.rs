/// One text file retained by a cross-language repository scan.
#[derive(Debug)]
pub struct CorpusFile {
    pub path: String,
    pub text: String,
}
