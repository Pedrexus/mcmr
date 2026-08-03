use crate::discovery::Scope;
use crate::protocol::RepositoryPath;
use std::path::Path;

mod contracts;
mod quoted;

pub use contracts::{CorpusFile, Mention};
use quoted::QuotedText;

/// The text of one repository, as the scans that read across languages need it.
///
/// A seam between two languages is stated in a manifest, an attribute, or a bare string, and no
/// single parser covers all three, so the scans that look for one are lexical and every one of them
/// begins the same way. Each walks a root, follows its Git ignores, keeps whatever reads as text,
/// and then asks the same question of it: where else does somebody name this. What differs between
/// scans is only which files are worth opening, so that is the one choice a caller states.
#[derive(Debug)]
pub struct Corpus {
    files: Vec<CorpusFile>,
}

impl Corpus {
    /// Read every file under one root that a scan wants, each with the relative path it was at.
    ///
    /// The scope decides which subtrees exist at all, and it is the same one the walk that builds
    /// the facts used. A scan carrying its own idea of what to skip would report an artifact out
    /// of a dependency tree the caller excluded, which is a finding about code nobody wrote.
    pub fn read(
        root: &Path,
        scope: &Scope,
        wanted: impl Fn(&str) -> bool,
    ) -> Result<Self, String> {
        let mut files = Vec::new();
        let mut walker = walkdir::WalkDir::new(root).into_iter();
        while let Some(found) = walker.next() {
            let entry =
                found.map_err(|failure| format!("repository corpus walk failed: {failure}"))?;
            let path = entry.path();
            let relative = RepositoryPath::new(path).relative_to(root, "corpus")?;
            if entry.file_type().is_dir() && scope.excludes_directory(&relative) {
                walker.skip_current_dir();
                continue;
            }
            if !entry.file_type().is_file() || scope.excludes(&relative) || !wanted(&relative) {
                continue;
            }
            let text = std::fs::read_to_string(path).map_err(|failure| {
                format!("corpus file {relative} could not be read as UTF-8: {failure}")
            })?;
            files.push(CorpusFile {
                path: relative,
                text,
            });
        }
        Ok(Self { files })
    }

    /// Return each file as the relative path it was found at and the text it holds.
    pub fn files(&self) -> &[CorpusFile] {
        &self.files
    }

    /// Return every file other than one declaring file that names something, and the line it did.
    ///
    /// A name that crosses a language boundary travels as text, a command to spawn, a library to
    /// load, or a path to request. Requiring the quotes keeps a coincidental substring from reading
    /// as a dependency, which a bare search cannot tell apart. The file that declared the thing is
    /// left out because naming what you yourself declare is not a reference to it.
    pub fn mentions(&self, mention: Mention<'_>) -> impl Iterator<Item = (&str, usize)> {
        self.files.iter().filter_map(move |file| {
            if file.path == mention.declared_in {
                return None;
            }
            file.text
                .quoted_line(mention.name)
                .map(|line| (file.path.as_str(), line))
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    fn corpus(files: &[(&str, &str)]) -> Corpus {
        Corpus {
            files: files
                .iter()
                .map(|(path, text)| CorpusFile {
                    path: (*path).to_string(),
                    text: (*text).to_string(),
                })
                .collect(),
        }
    }

    #[test]
    fn only_a_quoted_name_counts_as_naming_something() {
        let text = "spawn(\"mcmr-kernel\")\nlet mcmr_kernel = 1;\n";

        assert_eq!(text.quoted_line("mcmr-kernel"), Some(1));
        assert_eq!(text.quoted_line("mcmr_kernel"), None);
    }

    #[test]
    fn the_file_that_declared_a_name_is_not_a_reference_to_it() {
        let held = corpus(&[
            ("Cargo.toml", "name = \"mcmr-kernel\"\n"),
            ("run.py", "import os\nrun([\"mcmr-kernel\"])\n"),
        ]);

        assert_eq!(
            held.mentions(Mention {
                name: "mcmr-kernel",
                declared_in: "Cargo.toml",
            })
            .collect::<Vec<_>>(),
            vec![("run.py", 2)]
        );
    }

    #[test]
    fn a_walk_keeps_the_files_a_scan_asked_for_and_nothing_else() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let scope = crate::discovery::Scope::of(root, &[]);
        let held = Corpus::read(root, &scope, |path| path.ends_with("Cargo.toml"))
            .expect("the repository corpus is readable");

        assert_eq!(
            held.files()
                .iter()
                .map(|file| file.path.as_str())
                .collect::<Vec<_>>(),
            vec!["Cargo.toml"]
        );
    }

    #[test]
    fn a_scan_has_no_private_depth_ceiling_and_obeys_git_ignores() {
        static COUNTER: AtomicUsize = AtomicUsize::new(0);
        let root = std::env::temp_dir().join(format!(
            "mcmr-lexical-{}-{}",
            std::process::id(),
            COUNTER.fetch_add(1, Ordering::Relaxed)
        ));
        let deep = (0..18)
            .map(|index| format!("level{index}"))
            .collect::<Vec<_>>()
            .join("/");
        let manifest = root.join(&deep).join("Cargo.toml");
        let ignored = root.join("generated/Cargo.toml");
        std::fs::create_dir_all(manifest.parent().expect("the file has a parent")).unwrap();
        std::fs::create_dir_all(ignored.parent().expect("the file has a parent")).unwrap();
        std::fs::write(root.join(".gitignore"), "generated/\n").unwrap();
        std::fs::write(&manifest, "[package]\nname = \"deep\"\n").unwrap();
        std::fs::write(ignored, "[package]\nname = \"generated\"\n").unwrap();

        let scope = crate::discovery::Scope::of(&root, &[]);
        let held = Corpus::read(&root, &scope, |path| path.ends_with("Cargo.toml"))
            .expect("the repository corpus is readable");

        assert_eq!(held.files().len(), 1);
        assert_eq!(held.files()[0].path, format!("{deep}/Cargo.toml"));
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn a_requested_file_that_is_not_utf8_fails_the_scan() {
        static COUNTER: AtomicUsize = AtomicUsize::new(0);
        let root = std::env::temp_dir().join(format!(
            "mcmr-lexical-invalid-{}-{}",
            std::process::id(),
            COUNTER.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir_all(&root).unwrap();
        std::fs::write(root.join("Cargo.toml"), [0xff]).unwrap();

        let scope = crate::discovery::Scope::of(&root, &[]);
        let failure = Corpus::read(&root, &scope, |path| path.ends_with("Cargo.toml"))
            .expect_err("invalid source cannot become an empty corpus");

        assert!(failure.contains("Cargo.toml could not be read as UTF-8"));
        std::fs::remove_dir_all(root).unwrap();
    }
}
