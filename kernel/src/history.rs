use serde::Serialize;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;
use std::process::Command;

/// How much history one read covers, and how much of one commit is allowed to speak.
///
/// History is unbounded and a fact is not, so every field here is a ceiling rather than a
/// preference. `commits` is 2000 because that is several years of an active repository, reads in a
/// few milliseconds, and stops a decade-old project from handing us a hundred thousand commits
/// whose oldest half describes files nobody has opened since. `sweep` is 30 because a commit
/// touching more files than that is a reformat, a mass rename, or a dependency bump rather than a
/// focused edit, and the pairs it would mint couple everything to everything. `pairs` is 2000
/// because the pair map grows with the square of the files one commit touches, so the fact carries
/// the strongest evidence rather than all of it.
#[derive(Clone, Copy, Debug)]
pub struct Bounds {
    pub commits: usize,
    pub sweep: usize,
    pub pairs: usize,
}

impl Default for Bounds {
    fn default() -> Self {
        Self {
            commits: 2_000,
            sweep: 30,
            pairs: 2_000,
        }
    }
}

/// What the repository's own history says about each file and each pair of files.
#[derive(Clone, Debug, Default, Serialize)]
pub struct History {
    pub commit_count: usize,
    pub files: Vec<FileHistory>,
    pub pairs: Vec<CoChange>,
}

impl History {
    /// Return this history narrowed to the files one request is about.
    ///
    /// The commit count stays whole, because how much a repository changed is a fact about the
    /// repository rather than about the files a caller selected. A pair survives only when both
    /// of its halves do, since co-change is a claim about two files and half of one says nothing.
    fn retaining(&self, scope: &crate::discovery::Scope) -> Self {
        Self {
            commit_count: self.commit_count,
            files: self
                .files
                .iter()
                .filter(|file| scope.holds(&file.path))
                .cloned()
                .collect(),
            pairs: self
                .pairs
                .iter()
                .filter(|pair| scope.holds(&pair.left) && scope.holds(&pair.right))
                .cloned()
                .collect(),
        }
    }
}

/// How often one file changed, how many hands changed it, and how long ago that stopped.
#[derive(Clone, Debug, Serialize)]
pub struct FileHistory {
    pub path: String,
    pub commit_count: usize,
    pub author_count: usize,
    pub days_since_last_change: i64,
    pub line_count: usize,
    pub is_test: bool,
}

/// Two files that keep arriving in the same commit, and whether either one names the other.
#[derive(Clone, Debug, Serialize)]
pub struct CoChange {
    pub left: String,
    pub right: String,
    pub shared_commit_count: usize,
    pub left_commit_count: usize,
    pub right_commit_count: usize,
    pub import_reference_count: usize,
}

/// Read what the repository's own history says about each file and each pair of files.
///
/// Complexity alone names a file that is hard to read. Complexity beside churn names one that is
/// hard to read and keeps being read, which is a different and more urgent thing. Two files that
/// keep changing in the same commit are coupled whatever their imports say, and that coupling is
/// invisible to every other family here.
///
/// What is read is the files this request is about, since a caller that narrowed the request to
/// one language meant the history too. Ranking a Python module by churn in a run asked only about
/// CUDA names a file that run never opened.
pub fn read(root: &Path, scope: &crate::discovery::Scope) -> Vec<Value> {
    scan(root, Bounds::default())
        .as_ref()
        .map(|history| facts(&history.retaining(scope)))
        .unwrap_or_default()
}

/// Mine one bounded window of `git log`, or nothing where there is no history to mine.
///
/// Shelling out to `git` rather than linking a library is deliberate. `git log` is the one
/// interface every repository already answers, its output has been stable across a decade of
/// releases, and it is faster than any traversal we would write over the object store ourselves. A
/// directory that is not a repository, a repository with no commits, and a machine with no `git`
/// on it all take the same road out, which is nothing rather than a failure.
pub fn scan(root: &Path, bounds: Bounds) -> Option<History> {
    let commits = log(root, bounds.commits)?;
    let newest = commits
        .iter()
        .map(|commit| commit.seconds)
        .max()
        .unwrap_or_default();
    let mut tallies: BTreeMap<String, Tally> = BTreeMap::new();
    let mut support: BTreeMap<(String, String), usize> = BTreeMap::new();
    for commit in &commits {
        let touched: BTreeSet<&str> = commit.paths.iter().map(String::as_str).collect();
        let is_focused = touched.len() <= bounds.sweep;
        for path in &touched {
            let tally = tallies.entry((*path).to_string()).or_default();
            tally.commit_count += 1;
            tally.focused_count += usize::from(is_focused);
            tally.last_seconds = tally.last_seconds.max(commit.seconds);
            tally.authors.insert(commit.author.clone());
        }
        if !is_focused {
            continue;
        }
        let ordered: Vec<&str> = touched.into_iter().collect();
        for (index, left) in ordered.iter().enumerate() {
            for right in &ordered[index + 1..] {
                *support
                    .entry(((*left).to_string(), (*right).to_string()))
                    .or_default() += 1;
            }
        }
    }
    let contents = contents(root, &tallies);
    Some(History {
        commit_count: commits.len(),
        files: tallies
            .iter()
            .map(|(path, tally)| FileHistory {
                path: path.clone(),
                commit_count: tally.commit_count,
                author_count: tally.authors.len(),
                days_since_last_change: (newest - tally.last_seconds) / 86_400,
                line_count: contents.get(path).map_or(0, |content| content.line_count),
                is_test: is_test(path),
            })
            .collect(),
        pairs: coupled(support, &tallies, &contents, bounds.pairs),
    })
}

/// Return each pair strong enough to be worth carrying, strongest first.
///
/// A pair seen once is the overwhelming bulk of the map and proves nothing, so it never leaves
/// here. What survives is ranked by how often the two arrived together and cut at the ceiling, so
/// the fact holds the evidence a rule could act on rather than every coincidence in the log.
fn coupled(
    support: BTreeMap<(String, String), usize>,
    tallies: &BTreeMap<String, Tally>,
    contents: &BTreeMap<String, Content>,
    ceiling: usize,
) -> Vec<CoChange> {
    let mut ranked: Vec<((String, String), usize)> = support
        .into_iter()
        .filter(|(_, count)| *count > 1)
        .collect();
    ranked.sort_by(|left, right| right.1.cmp(&left.1).then_with(|| left.0.cmp(&right.0)));
    ranked.truncate(ceiling);
    ranked
        .into_iter()
        .map(|((left, right), shared)| CoChange {
            shared_commit_count: shared,
            left_commit_count: tallies.get(&left).map_or(0, |tally| tally.focused_count),
            right_commit_count: tallies.get(&right).map_or(0, |tally| tally.focused_count),
            import_reference_count: mentions(contents, &left, &right)
                + mentions(contents, &right, &left),
            left,
            right,
        })
        .collect()
}

/// One commit as the log states it, reduced to what the two collections need.
struct Commit {
    author: String,
    seconds: i64,
    paths: Vec<String>,
}

/// What one file collected across the window.
#[derive(Default)]
struct Tally {
    commit_count: usize,
    focused_count: usize,
    last_seconds: i64,
    authors: BTreeSet<String>,
}

/// How long one file is now, and the lines in it that name something else.
struct Content {
    line_count: usize,
    imports: Vec<String>,
}

/// The byte that opens a commit header, which no path and no status line can hold.
const MARKER: char = '\u{1}';

/// Ask `git` for one bounded window of history with the paths each commit touched.
///
/// `-M` turns on rename detection whatever the reader configured, so the rename lines the folding
/// below needs are always there. `--relative` reports paths against the scanned root and restricts
/// the log to it, which keeps a scan of one package inside a monorepo describing that package.
/// `--no-merges` drops a merge, which carries no diff of its own and would otherwise credit an
/// author and a date to files it never changed.
fn log(root: &Path, commits: usize) -> Option<Vec<Commit>> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args([
            "log",
            "-M",
            "--relative",
            "--name-status",
            "--no-merges",
            "--format=\u{1}%H\t%an\t%ct",
        ])
        .arg(format!("-n{commits}"))
        .output()
        .ok()?;
    output
        .status
        .success()
        .then(|| parse(&String::from_utf8_lossy(&output.stdout)))
}

/// Turn the log into commits whose paths are the names those files answer to today.
///
/// A `git mv` splits one file's history across two names, so a rename line is remembered and the
/// older name is folded onto the newer one. Without that a moved file loses the churn it earned
/// and leaves a phantom path behind that matches nothing on disk, which under-ranks exactly the
/// files somebody has already reorganized once.
fn parse(text: &str) -> Vec<Commit> {
    let mut commits: Vec<Commit> = Vec::new();
    let mut renames: BTreeMap<String, String> = BTreeMap::new();
    for line in text.split('\n') {
        if let Some(header) = line.strip_prefix(MARKER) {
            let mut fields = header.split('\t').skip(1);
            commits.push(Commit {
                author: fields.next().unwrap_or_default().to_string(),
                seconds: fields
                    .next()
                    .and_then(|value| value.parse().ok())
                    .unwrap_or(0),
                paths: Vec::new(),
            });
            continue;
        }
        let fields: Vec<&str> = line.split('\t').collect();
        let Some(commit) = commits.last_mut() else {
            continue;
        };
        // A rename or a copy states both names, and the commit itself touched the newer one. Only
        // a rename retires the older name, since a copy leaves the original where it was.
        if fields.len() == 3 && fields[0].starts_with(['R', 'C']) {
            commit.paths.push(fields[2].to_string());
            if fields[0].starts_with('R') {
                renames.insert(fields[1].to_string(), fields[2].to_string());
            }
        } else if fields.len() >= 2 && !fields[1].is_empty() {
            commit.paths.push(fields[1].to_string());
        }
    }
    for commit in &mut commits {
        commit.paths = commit
            .paths
            .iter()
            .map(|path| fold(&renames, path))
            .filter(|path| is_source(path))
            .collect();
    }
    commits
}

/// Follow one path through the rename chain to the name it answers to today.
fn fold(renames: &BTreeMap<String, String>, path: &str) -> String {
    let mut current = path.to_string();
    let mut seen = BTreeSet::from([current.clone()]);
    while let Some(next) = renames.get(&current) {
        current = next.clone();
        if !seen.insert(current.clone()) {
            break;
        }
    }
    current
}

/// Whether one path is source this kernel reads, which is what the two collections describe.
fn is_source(path: &str) -> bool {
    matches!(
        path.rsplit('.').next().unwrap_or_default(),
        "py" | "pyi"
            | "rs"
            | "ts"
            | "tsx"
            | "mts"
            | "cts"
            | "cu"
            | "cuh"
            | "cpp"
            | "cc"
            | "cxx"
            | "hpp"
            | "hh"
            | "c"
            | "h"
    )
}

/// Whether one path holds tests, which the conventions of six languages spell a few ways.
///
/// A test and the code it exercises change together by design, so a rule about coupling needs to
/// know which is which. Where that line sits is a judgment, so the kernel states the convention
/// and leaves the rule to decide whether it matters.
fn is_test(path: &str) -> bool {
    let file = path.rsplit('/').next().unwrap_or(path);
    file.starts_with("test_")
        || file == "conftest.py"
        || ["_test.", ".test.", ".spec."]
            .iter()
            .any(|marker| file.contains(marker))
        || path
            .split('/')
            .rev()
            .skip(1)
            .any(|part| matches!(part, "test" | "tests" | "testing" | "__tests__"))
}

/// Read how long each surviving file is and which of its lines name something else.
///
/// A path the log holds may have been deleted since, and that is not a failure. It keeps the churn
/// it earned, reads as zero lines, and so never surfaces as a file worth reopening.
fn contents(root: &Path, tallies: &BTreeMap<String, Tally>) -> BTreeMap<String, Content> {
    tallies
        .keys()
        .filter_map(|path| {
            let text = std::fs::read_to_string(root.join(path)).ok()?;
            Some((
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
            ))
        })
        .collect()
}

/// Whether one line is the shape a language states a dependency in.
fn is_import(line: &str) -> bool {
    [
        "import ", "from ", "use ", "pub use ", "#include", "export ",
    ]
    .iter()
    .any(|opener| line.starts_with(opener))
        || line.contains("require(")
}

/// Count the import lines of one file that name the other by the name it is known under.
///
/// This is lexical on purpose. The graph resolves an import properly, and the graph is built after
/// this pass and behind a different request, so a rule reading history alone would otherwise have
/// no way to tell a pair the structure already explains from a pair it does not. A count rather
/// than a verdict keeps the judgment where it belongs, which is in the rule.
fn mentions(contents: &BTreeMap<String, Content>, reader: &str, subject: &str) -> usize {
    let name = stem(subject);
    contents.get(reader).map_or(0, |content| {
        content
            .imports
            .iter()
            .filter(|line| names(line, name))
            .count()
    })
}

/// Return the name one file is imported under, which is not always the name of the file.
fn stem(path: &str) -> &str {
    let file = path.rsplit('/').next().unwrap_or(path);
    let base = file.split('.').next().unwrap_or(file);
    // These are named for the position they hold rather than for what they hold, so an import
    // reaches them by the name of the directory around them.
    if matches!(base, "__init__" | "mod" | "lib" | "index" | "main") {
        return path.rsplit('/').nth(1).unwrap_or(base);
    }
    base
}

/// Whether one line states a name as a whole word rather than inside a longer one.
fn names(line: &str, subject: &str) -> bool {
    !subject.is_empty()
        && line.match_indices(subject).any(|(position, _)| {
            let before = line[..position].chars().next_back();
            let after = line[position + subject.len()..].chars().next();
            !before.is_some_and(is_identifier) && !after.is_some_and(is_identifier)
        })
}

fn is_identifier(letter: char) -> bool {
    letter.is_alphanumeric() || letter == '_'
}

/// Return the one fact carrying both collections, since neither is read without the other.
pub fn facts(history: &History) -> Vec<Value> {
    vec![json!({
        "key": "history",
        "span": {"path": ""},
        "commit_count": history.commit_count,
        "files": history.files,
        "pairs": history.pairs,
    })]
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    /// One request asking about Python alone, which is what the fixtures below write.
    fn python_scope() -> crate::discovery::Scope {
        crate::discovery::Scope::of(&[], &[".py".to_string()]).expect("the patterns compile")
    }

    /// One throwaway repository, built commit by commit and removed when the test ends.
    struct Repository {
        root: std::path::PathBuf,
    }

    impl Repository {
        fn new(name: &str) -> Self {
            static COUNTER: AtomicUsize = AtomicUsize::new(0);
            let unique = COUNTER.fetch_add(1, Ordering::Relaxed);
            let root = std::env::temp_dir().join(format!(
                "mcmr-history-{}-{name}-{unique}",
                std::process::id()
            ));
            let _ = std::fs::remove_dir_all(&root);
            std::fs::create_dir_all(&root).expect("the temporary root is writable");
            let repository = Self { root };
            repository.git(&["init", "--quiet"]);
            repository.git(&["config", "user.email", "history@example.com"]);
            repository.git(&["config", "user.name", "First Author"]);
            repository.git(&["config", "commit.gpgsign", "false"]);
            repository
        }

        fn git(&self, arguments: &[&str]) {
            let finished = Command::new("git")
                .arg("-C")
                .arg(&self.root)
                .args(arguments)
                .env("GIT_CONFIG_GLOBAL", "/dev/null")
                .env("GIT_CONFIG_SYSTEM", "/dev/null")
                .output()
                .expect("git answers");
            assert!(finished.status.success(), "git {arguments:?} failed");
        }

        fn write(&self, path: &str, text: &str) {
            let full = self.root.join(path);
            std::fs::write(full, text).expect("the file is writable");
        }

        fn remove(&self, path: &str) {
            std::fs::remove_file(self.root.join(path)).expect("the file is removable");
        }

        /// Commit everything staged at a stated day, so a date assertion is reproducible.
        fn commit(&self, message: &str, author: &str, day: &str) {
            self.git(&["add", "-A"]);
            let stamp = format!("{day}T12:00:00+00:00");
            let finished = Command::new("git")
                .arg("-C")
                .arg(&self.root)
                .args(["commit", "--quiet", "-m", message, "--author"])
                .arg(format!("{author} <{author}@example.com>"))
                .env("GIT_CONFIG_GLOBAL", "/dev/null")
                .env("GIT_CONFIG_SYSTEM", "/dev/null")
                .env("GIT_AUTHOR_DATE", &stamp)
                .env("GIT_COMMITTER_DATE", &stamp)
                .output()
                .expect("git answers");
            assert!(finished.status.success(), "the commit failed");
        }
    }

    impl Drop for Repository {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.root);
        }
    }

    fn history(repository: &Repository) -> History {
        scan(&repository.root, Bounds::default()).expect("the throwaway repository has history")
    }

    fn file<'a>(history: &'a History, path: &str) -> &'a FileHistory {
        history
            .files
            .iter()
            .find(|entry| entry.path == path)
            .expect("the file is in the history")
    }

    #[test]
    fn a_directory_outside_a_repository_reports_nothing_rather_than_failing() {
        let outside =
            std::env::temp_dir().join(format!("mcmr-history-bare-{}", std::process::id()));
        std::fs::create_dir_all(&outside).expect("the temporary root is writable");

        assert!(read(&outside, &python_scope()).is_empty());
        assert!(scan(&outside, Bounds::default()).is_none());

        let _ = std::fs::remove_dir_all(&outside);
    }

    #[test]
    fn each_file_carries_its_commits_its_authors_and_how_long_ago_it_stopped() {
        let repository = Repository::new("counts");
        repository.write("engine.py", "import parser\n");
        repository.write("parser.py", "value = 1\n");
        repository.commit("first", "First Author", "2026-01-01");
        repository.write("engine.py", "import parser\nvalue = 2\n");
        repository.commit("second", "Second Author", "2026-01-11");
        repository.write("engine.py", "import parser\nvalue = 3\n");
        repository.commit("third", "First Author", "2026-01-21");

        let read = history(&repository);

        assert_eq!(read.commit_count, 3);
        assert_eq!(file(&read, "engine.py").commit_count, 3);
        assert_eq!(file(&read, "engine.py").author_count, 2);
        assert_eq!(file(&read, "engine.py").days_since_last_change, 0);
        assert_eq!(file(&read, "engine.py").line_count, 2);
        assert_eq!(file(&read, "parser.py").commit_count, 1);
        assert_eq!(file(&read, "parser.py").author_count, 1);
        assert_eq!(file(&read, "parser.py").days_since_last_change, 20);
    }

    #[test]
    fn a_day_count_is_read_against_the_newest_commit_rather_than_against_today() {
        let repository = Repository::new("clock");
        repository.write("stable.py", "value = 1\n");
        repository.commit("first", "First Author", "2019-03-01");
        repository.write("moving.py", "value = 2\n");
        repository.commit("second", "First Author", "2019-03-31");

        // Both commits are years old, so a count against the wall clock would grow on every run
        // and these two files would never sit exactly thirty days apart.
        let read = history(&repository);

        assert_eq!(file(&read, "stable.py").days_since_last_change, 30);
        assert_eq!(file(&read, "moving.py").days_since_last_change, 0);
    }

    #[test]
    fn two_files_that_keep_arriving_together_are_reported_as_one_pair() {
        let repository = Repository::new("pairs");
        for day in 1..=3 {
            repository.write("reader.py", &format!("value = {day}\n"));
            repository.write("writer.py", &format!("value = {day}\n"));
            repository.write("alone.py", &format!("value = {day}\n"));
            repository.commit("edit", "First Author", &format!("2026-02-0{day}"));
            repository.write("alone.py", &format!("extra = {day}\n"));
            repository.commit("alone", "First Author", &format!("2026-02-1{day}"));
        }

        let read = history(&repository);
        let coupled = read
            .pairs
            .iter()
            .find(|pair| pair.left == "reader.py" && pair.right == "writer.py")
            .expect("the two files co-changed");

        assert_eq!(coupled.shared_commit_count, 3);
        assert_eq!(coupled.left_commit_count, 3);
        assert_eq!(coupled.right_commit_count, 3);
        assert_eq!(coupled.import_reference_count, 0);
        assert_eq!(file(&read, "alone.py").commit_count, 6);
    }

    #[test]
    fn a_pair_says_how_many_of_its_import_lines_name_the_other() {
        let repository = Repository::new("imports");
        for day in 1..=3 {
            repository.write(
                "reader.py",
                &format!("from . import writer\nvalue = {day}\n"),
            );
            repository.write("writer.py", &format!("value = {day}\n"));
            repository.commit("edit", "First Author", &format!("2026-03-0{day}"));
        }

        let read = history(&repository);

        assert_eq!(read.pairs[0].import_reference_count, 1);
    }

    #[test]
    fn a_sweeping_commit_still_counts_as_churn_but_never_couples_what_it_touched() {
        let repository = Repository::new("sweep");
        for index in 0..4 {
            repository.write(&format!("module{index}.py"), "value = 1\n");
        }
        repository.commit("first", "First Author", "2026-04-01");
        for index in 0..4 {
            repository.write(&format!("module{index}.py"), "value = 2\n");
        }
        repository.commit("sweep", "First Author", "2026-04-02");

        let narrow = scan(
            &repository.root,
            Bounds {
                sweep: 3,
                ..Bounds::default()
            },
        )
        .expect("the throwaway repository has history");

        assert_eq!(file(&narrow, "module0.py").commit_count, 2);
        assert!(narrow.pairs.is_empty());
        assert_eq!(history(&repository).pairs.len(), 6);
    }

    #[test]
    fn a_renamed_file_keeps_the_history_it_earned_under_its_old_name() {
        let repository = Repository::new("rename");
        repository.write("old.py", "value = 1\n");
        repository.commit("first", "First Author", "2026-05-01");
        repository.write("old.py", "value = 2\n");
        repository.commit("second", "First Author", "2026-05-02");
        repository.git(&["mv", "old.py", "new.py"]);
        repository.commit("rename", "First Author", "2026-05-03");

        let read = history(&repository);

        assert_eq!(file(&read, "new.py").commit_count, 3);
        assert!(read.files.iter().all(|entry| entry.path != "old.py"));
    }

    #[test]
    fn a_deleted_file_keeps_its_churn_and_reads_as_no_lines_at_all() {
        let repository = Repository::new("deleted");
        repository.write("gone.py", "value = 1\n");
        repository.commit("first", "First Author", "2026-06-01");
        repository.remove("gone.py");
        repository.commit("second", "First Author", "2026-06-02");

        let read = history(&repository);

        assert_eq!(file(&read, "gone.py").commit_count, 2);
        assert_eq!(file(&read, "gone.py").line_count, 0);
    }

    #[test]
    fn the_commit_ceiling_reads_the_recent_window_and_leaves_the_rest() {
        let repository = Repository::new("ceiling");
        for day in 1..=4 {
            repository.write("engine.py", &format!("value = {day}\n"));
            repository.commit("edit", "First Author", &format!("2026-07-0{day}"));
        }

        let recent = scan(
            &repository.root,
            Bounds {
                commits: 2,
                ..Bounds::default()
            },
        )
        .expect("the throwaway repository has history");

        assert_eq!(recent.commit_count, 2);
        assert_eq!(file(&recent, "engine.py").commit_count, 2);
    }

    #[test]
    fn the_pair_ceiling_keeps_the_strongest_evidence_and_drops_the_rest() {
        let repository = Repository::new("pair-ceiling");
        for day in 1..=3 {
            for index in 0..3 {
                repository.write(&format!("module{index}.py"), &format!("value = {day}\n"));
            }
            repository.commit("edit", "First Author", &format!("2026-08-0{day}"));
        }

        let capped = scan(
            &repository.root,
            Bounds {
                pairs: 1,
                ..Bounds::default()
            },
        )
        .expect("the throwaway repository has history");

        assert_eq!(capped.pairs.len(), 1);
        assert_eq!(capped.pairs[0].shared_commit_count, 3);
    }

    #[test]
    fn the_history_answers_for_the_files_the_same_request_would_have_read() {
        let repository = Repository::new("scoped");
        repository.write("engine.py", "value = 1\n");
        repository.write("kernel.cu", "__global__ void scale() {}\n");
        repository.commit("first", "First Author", "2026-09-01");
        repository.write("engine.py", "value = 2\n");
        repository.write("kernel.cu", "__global__ void scale(int n) {}\n");
        repository.commit("second", "First Author", "2026-09-02");

        let native =
            crate::discovery::Scope::of(&[], &[".cu".to_string()]).expect("the patterns compile");
        let emitted = read(&repository.root, &native);
        let named: Vec<&str> = emitted[0]["files"]
            .as_array()
            .expect("a file list")
            .iter()
            .map(|file| file["path"].as_str().unwrap_or_default())
            .collect();

        // Ranking a Python module by churn in a run asked only about CUDA names a file that run
        // never opened, and a pair survives only when both of its halves do.
        assert_eq!(named, vec!["kernel.cu"]);
        assert_eq!(emitted[0]["commit_count"], 2);
        assert!(
            emitted[0]["pairs"]
                .as_array()
                .expect("a pair list")
                .is_empty()
        );
        assert_eq!(
            read(&repository.root, &python_scope())[0]["files"]
                .as_array()
                .expect("a file list")
                .len(),
            1
        );
    }

    #[test]
    fn one_fact_carries_both_collections_because_neither_is_read_without_the_other() {
        let repository = Repository::new("fact");
        repository.write("engine.py", "value = 1\n");
        repository.commit("first", "First Author", "2026-09-01");

        let emitted = read(&repository.root, &python_scope());

        assert_eq!(emitted.len(), 1);
        assert_eq!(emitted[0]["key"], "history");
        assert!(emitted[0]["files"].is_array());
        assert!(emitted[0]["pairs"].is_array());
    }

    #[test]
    fn a_name_is_only_matched_where_the_line_states_it_whole() {
        assert!(names("from . import writer", "writer"));
        assert!(!names("from . import writerless", "writer"));
        assert!(!names("", "writer"));
        assert_eq!(stem("package/__init__.py"), "package");
        assert_eq!(stem("crate/src/lib.rs"), "src");
        assert_eq!(stem("engine.py"), "engine");
        assert_eq!(stem("lib.rs"), "lib");
        assert!(is_import("#include <vector>"));
        assert!(is_import("const parser = require('./parser')"));
        assert!(!is_import("value = 1"));
        assert!(!is_source("README.md"));
    }

    #[test]
    fn a_test_says_so_however_its_language_spells_the_convention() {
        assert!(is_test("tests/test_engine.py"));
        assert!(is_test("src/conftest.py"));
        assert!(is_test("src/engine_test.rs"));
        assert!(is_test("web/engine.spec.ts"));
        assert!(is_test("src/__tests__/engine.ts"));
        assert!(!is_test("src/engine.py"));
        assert!(!is_test("src/latest.py"));
    }
}
