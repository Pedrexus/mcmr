mod content;

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use content::Content;

/// What one file collected across the history window.
#[derive(Default)]
pub(super) struct Tally {
    pub(super) commit_count: usize,
    pub(super) last_seconds: i64,
    pub(super) authors: BTreeSet<String>,
}

/// Read how long each surviving file is and which of its lines name something else.
pub(super) fn contents(
    root: &Path,
    tallies: &BTreeMap<String, Tally>,
) -> Result<BTreeMap<String, Content>, String> {
    let mut contents = BTreeMap::new();
    for path in tallies.keys() {
        let full = root.join(path);
        let text = match std::fs::read_to_string(&full) {
            Ok(text) => text,
            Err(failure) if failure.kind() == std::io::ErrorKind::NotFound => continue,
            Err(failure) => {
                return Err(format!(
                    "history file {path} could not be read as UTF-8: {failure}"
                ));
            }
        };
        contents.insert(
            path.clone(),
            Content {
                line_count: text.lines().count(),
                imports: text
                    .lines()
                    .map(str::trim)
                    .filter(|line| is_import(line))
                    .map(str::to_string)
                    .collect(),
            },
        );
    }
    Ok(contents)
}

/// Whether one line is the shape a language states a dependency in.
pub(super) fn is_import(line: &str) -> bool {
    [
        "import ", "from ", "use ", "pub use ", "#include", "export ",
    ]
    .iter()
    .any(|opener| line.starts_with(opener))
        || line.contains("require(")
}
