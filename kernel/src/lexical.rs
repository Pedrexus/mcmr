use crate::discovery::Scope;
use std::path::Path;

/// The text of one repository, as the scans that read across languages need it.
///
/// A seam between two languages is stated in a manifest, an attribute, or a bare string, and no
/// single parser covers all three, so the scans that look for one are lexical and every one of them
/// begins the same way. Each walks a root, refuses the directories holding code the repository did
/// not write, keeps whatever reads as text, and then asks the same question of it: where else does
/// somebody name this. What differs between them is only how deep it is worth descending and which
/// files are worth opening, so those are the two things a caller states.
pub struct Corpus {
    files: Vec<(String, String)>,
}

impl Corpus {
    /// Read every file under one root that a scan wants, each with the relative path it was at.
    ///
    /// The scope decides which subtrees exist at all, and it is the same one the walk that builds
    /// the facts used. A scan carrying its own idea of what to skip would report an artifact out
    /// of a dependency tree the caller excluded, which is a finding about code nobody wrote.
    pub fn read(root: &Path, depth: usize, scope: &Scope, wanted: impl Fn(&str) -> bool) -> Self {
        let mut files = Vec::new();
        for entry in walkdir::WalkDir::new(root)
            .max_depth(depth)
            .into_iter()
            .filter_entry(|entry| !scope.excludes_directory(&Self::relative(root, entry.path())))
            .filter_map(Result::ok)
        {
            let path = entry.path();
            let relative = Self::relative(root, path);
            if !entry.file_type().is_file() || scope.excludes(&relative) || !wanted(&relative) {
                continue;
            }
            if let Ok(text) = std::fs::read_to_string(path) {
                files.push((relative, text));
            }
        }
        Self { files }
    }

    fn relative(root: &Path, path: &Path) -> String {
        path.strip_prefix(root)
            .unwrap_or(path)
            .to_string_lossy()
            .replace('\\', "/")
    }

    /// Return each file as the relative path it was found at and the text it holds.
    pub fn files(&self) -> &[(String, String)] {
        &self.files
    }

    /// Return every file other than one declaring file that names something, and the line it did.
    ///
    /// A name that crosses a language boundary travels as text, a command to spawn, a library to
    /// load, or a path to request. Requiring the quotes keeps a coincidental substring from reading
    /// as a dependency, which a bare search cannot tell apart. The file that declared the thing is
    /// left out because naming what you yourself declare is not a reference to it.
    pub fn mentions(&self, name: &str, declared_in: &str) -> impl Iterator<Item = (&str, usize)> {
        self.files.iter().filter_map(move |(path, text)| {
            if path == declared_in {
                return None;
            }
            Self::quoted(text, name).map(|line| (path.as_str(), line))
        })
    }

    /// Return the line where one text names something inside quotes, when it names it at all.
    fn quoted(text: &str, name: &str) -> Option<usize> {
        let needles = [
            format!("\"{name}\""),
            format!("'{name}'"),
            format!("`{name}`"),
        ];
        text.lines()
            .enumerate()
            .find(|(_, line)| needles.iter().any(|needle| line.contains(needle.as_str())))
            .map(|(index, _)| index + 1)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn corpus(files: &[(&str, &str)]) -> Corpus {
        Corpus {
            files: files
                .iter()
                .map(|(path, text)| ((*path).to_string(), (*text).to_string()))
                .collect(),
        }
    }

    #[test]
    fn only_a_quoted_name_counts_as_naming_something() {
        let text = "spawn(\"mcmr-kernel\")\nlet mcmr_kernel = 1;\n";

        assert_eq!(Corpus::quoted(text, "mcmr-kernel"), Some(1));
        assert_eq!(Corpus::quoted(text, "mcmr_kernel"), None);
    }

    #[test]
    fn the_file_that_declared_a_name_is_not_a_reference_to_it() {
        let held = corpus(&[
            ("Cargo.toml", "name = \"mcmr-kernel\"\n"),
            ("run.py", "import os\nrun([\"mcmr-kernel\"])\n"),
        ]);

        assert_eq!(
            held.mentions("mcmr-kernel", "Cargo.toml")
                .collect::<Vec<_>>(),
            vec![("run.py", 2)]
        );
    }

    #[test]
    fn a_walk_keeps_the_files_a_scan_asked_for_and_nothing_else() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let scope = crate::discovery::Scope::of(&[], &[]).expect("the patterns compile");
        let held = Corpus::read(root, 2, &scope, |path| path.ends_with("Cargo.toml"));

        assert_eq!(
            held.files()
                .iter()
                .map(|(path, _)| path.as_str())
                .collect::<Vec<_>>(),
            vec!["Cargo.toml"]
        );
    }
}
