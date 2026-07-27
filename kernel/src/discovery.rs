use crate::protocol::Request;
use globset::{Glob, GlobSet, GlobSetBuilder};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;
use walkdir::WalkDir;

/// One source file the kernel read once for every family that needs it.
pub struct Document {
    pub relative: String,
    pub source: String,
}

/// One directory the walk met, described by what it holds rather than by what was parsed in it.
///
/// A directory is not a language construct, so nothing here comes from a frontend. Deriving these
/// counts from the files a frontend parsed would make a directory holding no source invisible,
/// and that is precisely the directory a rule about empty directories has to be able to see.
#[derive(Debug, Default)]
pub struct Directory {
    pub relative: String,
    pub visible_entry_count: usize,
    pub direct_module_count: usize,
    pub is_ignored: bool,
    pub is_retained: bool,
}

/// Everything one walk of a repository found, which is its source files and its directories.
pub struct Inventory {
    pub documents: Vec<Document>,
    pub directories: Vec<Directory>,
}

/// The names a project writes into a directory so version control keeps it while it holds nothing.
///
/// Git stores files rather than directories, so an intentionally empty folder only survives a
/// clone because one of these sits in it. Meeting one is what tells a retained placeholder apart
/// from a folder somebody emptied and forgot.
const RETAINERS: [&str; 4] = [".gitkeep", ".keep", ".placeholder", ".gitignore"];

/// Every directory this kernel never judges, whatever a caller asks for on top.
///
/// Three kinds of directory are here for one reason. A dependency tree, an environment, and a
/// tool's own cache hold files somebody installed. Build output and generated output hold files a
/// build wrote. Judging either tells a reader about code they cannot edit, and on a real project
/// the generated half is most of what a report says: a SvelteKit repository puts two thirds of its
/// findings inside `.svelte-kit`, which no reader can act on and no commit can change.
///
/// A directory a person edits must never be on this list, which is why each entry names the exact
/// directory one tool writes into rather than a word that might also name a source tree. That is
/// why `venv` and `coverage` are absent while `.venv` and `htmlcov` are present, and why nothing
/// here is a bare `out` or `tmp`.
const EXCLUDED: [&str; 34] = [
    "**/.git/**",
    "**/.venv/**",
    "**/node_modules/**",
    "**/__pycache__/**",
    "**/.chefe/**",
    "**/.pixi/**",
    "**/site-packages/**",
    "**/vendor/**",
    "**/vendored/**",
    "**/target/**",
    "**/build/**",
    "**/.build/**",
    "**/cmake-build-*/**",
    "**/dist/**",
    "**/.dist/**",
    "**/.mypy_cache/**",
    "**/.ruff_cache/**",
    "**/.pytest_cache/**",
    "**/.hypothesis/**",
    "**/.ipynb_checkpoints/**",
    "**/.tox/**",
    "**/.nox/**",
    "**/.eggs/**",
    "**/*.egg-info/**",
    "**/htmlcov/**",
    "**/.svelte-kit/**",
    "**/.next/**",
    "**/.nuxt/**",
    "**/.output/**",
    "**/.astro/**",
    "**/.angular/**",
    "**/.turbo/**",
    "**/.parcel-cache/**",
    "**/.wrangler/**",
];

/// Which files one request is about, which every pass asks rather than only the walk.
///
/// The walk is not the only thing that reads a repository. The cross-language scan, the route
/// scan, and the history pass each open their own view of the tree, and a caller who narrowed the
/// request meant all of them. Compiling the answer once and handing it to each is what stops
/// `--exclude` from holding for the files a rule reads and not for the artifacts one reports, and
/// `--suffixes` from holding for the source and not for the history.
pub struct Scope {
    excluded: GlobSet,
    suffixes: Vec<String>,
}

impl Scope {
    /// Compile what one request asks for, on top of the directories nothing ever judges.
    pub fn of(exclude: &[String], suffixes: &[String]) -> Result<Self, String> {
        let mut builder = GlobSetBuilder::new();
        for pattern in EXCLUDED
            .iter()
            .copied()
            .chain(exclude.iter().map(String::as_str))
        {
            builder.add(Glob::new(pattern).map_err(|failure| failure.to_string())?);
        }
        Ok(Self {
            excluded: builder.build().map_err(|failure| failure.to_string())?,
            suffixes: suffixes.to_vec(),
        })
    }

    /// Whether one repository-relative path is source this request asked to read.
    pub fn holds(&self, relative: &str) -> bool {
        !self.excludes(relative)
            && self
                .suffixes
                .iter()
                .any(|suffix| relative.ends_with(suffix.as_str()))
    }

    /// Whether the exclusion set removes one path.
    pub fn excludes(&self, relative: &str) -> bool {
        self.excluded.is_match(relative)
    }

    /// Whether the exclusion set removes one directory, which is what lets a walk skip its subtree.
    ///
    /// A pattern that excludes a directory is written for the paths inside it, the way
    /// `**/target/**` is, so the directory is matched as the prefix its own contents carry rather
    /// than as a bare name that no such pattern would ever hit.
    pub fn excludes_directory(&self, relative: &str) -> bool {
        !relative.is_empty() && (self.excludes(relative) || self.excludes(&format!("{relative}/")))
    }
}

/// Walk one root, reading every source file and recording every directory the walk scanned.
///
/// The directories are recorded as the walk meets them rather than derived from the files that
/// were read, because a directory holding no source file exists in the tree and in no document
/// list. A directory the exclusion set removes is neither recorded nor entered, so a checked-out
/// build tree costs one glob match rather than a fact per folder inside it. A dotted directory is
/// recorded once and what sits inside it is not described, since a tool's own state is read for
/// the source it holds and is not a layout anybody laid out.
pub fn collect(request: &Request, scope: &Scope) -> Result<Inventory, String> {
    let root = Path::new(&request.root);
    let mut documents = Vec::new();
    let mut directories: BTreeMap<String, Directory> = BTreeMap::new();
    let mut walker = WalkDir::new(root).into_iter();
    while let Some(found) = walker.next() {
        let Ok(entry) = found else { continue };
        let is_directory = entry.file_type().is_dir();
        if !is_directory && !entry.file_type().is_file() {
            continue;
        }
        let relative = relative_to(root, entry.path());
        let name = entry.file_name().to_string_lossy().into_owned();
        let holds = directory_of(&relative).to_string();
        let removed = match is_directory {
            true => scope.excludes_directory(&relative),
            false => scope.excludes(&relative),
        };
        if is_directory && removed {
            walker.skip_current_dir();
        } else if is_directory && is_described(&relative) {
            let held = directories.entry(relative.clone()).or_default();
            held.relative = relative.clone();
            held.is_ignored = is_hidden(&relative);
        }
        if relative.is_empty() {
            continue;
        }
        // A file that is not valid UTF-8 is not source this kernel can parse, so it is skipped
        // rather than reported as a parse failure it could never recover from.
        let source = (!is_directory && scope.holds(&relative))
            .then(|| std::fs::read_to_string(entry.path()).ok())
            .flatten();
        if is_described(&holds) {
            let parent = directories.entry(holds).or_default();
            parent.visible_entry_count += usize::from(!removed && !name.starts_with('.'));
            parent.direct_module_count += usize::from(source.is_some());
            parent.is_retained |= RETAINERS.contains(&name.as_str());
        }
        if let Some(read) = source {
            documents.push(Document {
                relative,
                source: read,
            });
        }
    }
    documents.sort_by(|left, right| left.relative.cmp(&right.relative));
    Ok(Inventory {
        documents,
        directories: directories.into_values().collect(),
    })
}

/// One fact per directory the walk met, stating what it holds and where it sits.
///
/// The family carries no language, because a directory holding Python beside Rust belongs to
/// neither and the graph already identifies one as a path rather than under a language.
pub fn directories(
    directories: &[Directory],
    roots: &SourceRoots,
    catalogs: &BTreeSet<String>,
) -> Vec<Value> {
    directories
        .iter()
        .map(|directory| {
            let label = match directory.relative.is_empty() {
                true => ".",
                false => &directory.relative,
            };
            json!({
                "key": format!("directory:{label}"),
                "span": {"path": label},
                "visible_entry_count": directory.visible_entry_count,
                "source_depth": roots.depth(&directory.relative),
                "direct_module_count": directory.direct_module_count,
                "is_ignored": directory.is_ignored,
                "is_retained": directory.is_retained,
                "is_definition_catalog": catalogs.contains(&directory.relative),
            })
        })
        .collect()
}

/// The directories whose every module declares exactly one thing.
///
/// A folder holding one class or one rule per file is wide because that is what it is for, so the
/// rule counting modules exempts it. Whether a module declares one thing is what every frontend
/// already answered in `ModuleFact`, so this reads that answer rather than parsing a second time.
/// A package initializer is left out, since it states what the directory is rather than adding
/// something a reader has to choose between.
pub fn definition_catalogs(modules: &[Value]) -> BTreeSet<String> {
    let mut declared: BTreeMap<String, Vec<u64>> = BTreeMap::new();
    for module in modules {
        if module["is_package_initializer"]
            .as_bool()
            .unwrap_or_default()
        {
            continue;
        }
        let path = module["span"]["path"].as_str().unwrap_or_default();
        let count = module["class_count"].as_u64().unwrap_or_default()
            + module["function_count"].as_u64().unwrap_or_default();
        declared
            .entry(directory_of(path).to_string())
            .or_default()
            .push(count);
    }
    declared
        .into_iter()
        .filter(|(_, counts)| counts.iter().all(|count| *count == 1))
        .map(|(directory, _)| directory)
        .collect()
}

/// Whether one path sits under a name every tool already treats as not part of the layout.
///
/// A leading dot is how this platform spells "this is machinery rather than the tree somebody
/// maintains", so a cache, a tool's own state, and an editor directory are all read for the source
/// they hold and reported with the flag that says nobody laid them out.
fn is_hidden(relative: &str) -> bool {
    relative.split('/').any(|part| part.starts_with('.'))
}

/// Whether one directory is described at all, which everything but the inside of a dotted one is.
///
/// The dotted directory itself is described, so a rule can see that it exists and decline it. What
/// sits inside it is not, because a generated output tree under `.svelte-kit` would otherwise cost
/// a fact and a depth measurement per folder for a layout nobody wrote.
fn is_described(relative: &str) -> bool {
    !is_hidden(directory_of(relative))
}

fn relative_to(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

/// The import roots of one repository, which decide what every module is called.
///
/// Python names a module by walking up from its file while each directory is a package, so the
/// first ancestor without an `__init__.py` is the root the import system sees. A monorepo holds
/// many of those roots, and reading them from the tree keeps `src` layouts, nested packages, and
/// bare scripts all naming themselves the way they name each other.
#[derive(Debug, Default)]
pub struct Packages {
    directories: BTreeSet<String>,
}

impl Packages {
    pub fn of(documents: &[Document]) -> Self {
        Self {
            directories: documents
                .iter()
                .filter(|document| document.relative.ends_with("/__init__.py"))
                .map(|document| directory_of(&document.relative).to_string())
                .collect(),
        }
    }

    /// Return every directory the import system starts naming a package chain from.
    ///
    /// The root is the first ancestor of a package that is not itself a package, which is exactly
    /// the boundary `module_name` stops walking up at, so a `src` layout, a nested package, and a
    /// flat layout at the repository root all report the directory their imports are written
    /// against.
    pub fn roots(&self) -> BTreeSet<String> {
        self.directories
            .iter()
            .map(|package| directory_of(package).to_string())
            .filter(|ancestor| !self.directories.contains(ancestor))
            .collect()
    }

    /// Return the dotted module name one repository-relative path declares.
    pub fn module_name(&self, relative: &str) -> String {
        let trimmed = relative.strip_suffix(".py").unwrap_or(relative);
        let trimmed = trimmed.strip_suffix("/__init__").unwrap_or(trimmed);
        let parts: Vec<&str> = trimmed.split('/').filter(|part| !part.is_empty()).collect();
        let mut root = parts.len().saturating_sub(1);
        while root > 0 && self.directories.contains(&parts[..root].join("/")) {
            root -= 1;
        }
        parts[root..].join(".")
    }
}

fn directory_of(path: &str) -> &str {
    path.rsplit_once('/').map(|(head, _)| head).unwrap_or("")
}

/// The crate roots of one repository, which decide what every Rust module is called.
///
/// Rust names a module by where it sits under the crate root, and the root is the directory whose
/// `src` holds a `lib.rs` or a `main.rs`. The crate is named by that directory, not by the package
/// name in the manifest, since two crates in one repository are told apart by where they live and
/// a manifest is not always a file this kernel was asked to read.
#[derive(Debug, Default)]
pub struct Crates {
    roots: BTreeSet<String>,
}

impl Crates {
    pub fn of(documents: &[Document]) -> Self {
        Self {
            roots: documents
                .iter()
                .filter_map(|document| {
                    let directory = directory_of(&document.relative);
                    let name = document.relative.rsplit('/').next().unwrap_or_default();
                    let is_root = matches!(name, "lib.rs" | "main.rs") && ends_in_src(directory);
                    is_root.then(|| directory.trim_end_matches("src").to_string())
                })
                .collect(),
        }
    }

    /// Return the path-separated module name one repository-relative path declares.
    pub fn module_name(&self, relative: &str) -> String {
        let root = self
            .roots
            .iter()
            .filter(|root| relative.starts_with(root.as_str()))
            .max_by_key(|root| root.len());
        let inside = root
            .map(|root| relative.trim_start_matches(root.as_str()))
            .unwrap_or(relative);
        let crate_name = root
            .map(|root| root.trim_end_matches('/'))
            .and_then(|root| root.rsplit('/').next())
            .filter(|name| !name.is_empty())
            .unwrap_or("crate");
        let trimmed = inside
            .trim_start_matches("src/")
            .strip_suffix(".rs")
            .unwrap_or(inside);
        let parts: Vec<&str> = trimmed
            .split('/')
            .filter(|part| !part.is_empty() && !matches!(*part, "lib" | "main" | "mod"))
            .collect();
        std::iter::once(crate_name)
            .chain(parts)
            .collect::<Vec<_>>()
            .join("::")
    }
}

fn ends_in_src(directory: &str) -> bool {
    directory == "src" || directory.ends_with("/src")
}

/// The directories this kernel starts naming modules from, which is what depth is measured against.
///
/// A path is only deep relative to where its language begins counting. Python begins at the first
/// ancestor that is not a package, Rust begins at the `src` beside a crate root, and every other
/// layout this kernel reads spells that boundary `src` as well, so those two answers are the whole
/// set. Reading them off the tree is what keeps the measure from needing a setting nobody updates.
#[derive(Debug, Default)]
pub struct SourceRoots {
    directories: BTreeSet<String>,
}

impl SourceRoots {
    pub fn of(directories: &[Directory], packages: &Packages) -> Self {
        Self {
            directories: directories
                .iter()
                .map(|directory| directory.relative.clone())
                .filter(|relative| ends_in_src(relative))
                .chain(packages.roots())
                .collect(),
        }
    }

    /// Return how many directory levels one directory sits below the source root above it.
    pub fn depth(&self, directory: &str) -> usize {
        let inside = self
            .directories
            .iter()
            .filter(|root| prefixes(root, directory))
            .max_by_key(|root| root.len())
            .and_then(|root| directory.strip_prefix(root.as_str()))
            .unwrap_or(directory);
        inside.split('/').filter(|part| !part.is_empty()).count()
    }
}

/// Whether one directory sits at or below another, compared by whole path components.
fn prefixes(root: &str, directory: &str) -> bool {
    root.is_empty() || directory == root || directory.starts_with(&format!("{root}/"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    fn document(relative: &str) -> Document {
        Document {
            relative: relative.to_string(),
            source: String::new(),
        }
    }

    /// One throwaway directory tree, written entry by entry and removed when the test ends.
    struct Tree {
        root: std::path::PathBuf,
    }

    impl Tree {
        fn new(name: &str) -> Self {
            static COUNTER: AtomicUsize = AtomicUsize::new(0);
            let unique = COUNTER.fetch_add(1, Ordering::Relaxed);
            let root = std::env::temp_dir().join(format!(
                "mcmr-discovery-{}-{name}-{unique}",
                std::process::id()
            ));
            let _ = std::fs::remove_dir_all(&root);
            std::fs::create_dir_all(&root).expect("the temporary root is writable");
            Self { root }
        }

        fn write(&self, relative: &str, source: &str) -> &Self {
            let path = self.root.join(relative);
            std::fs::create_dir_all(path.parent().expect("a written file sits in a directory"))
                .expect("the temporary root is writable");
            std::fs::write(path, source).expect("the temporary root is writable");
            self
        }

        fn directory(&self, relative: &str) -> &Self {
            std::fs::create_dir_all(self.root.join(relative))
                .expect("the temporary root is writable");
            self
        }

        fn walk(&self, exclude: &[&str]) -> Inventory {
            let patterns: Vec<String> = exclude
                .iter()
                .map(|pattern| (*pattern).to_string())
                .collect();
            let suffixes = vec![".py".to_string(), ".rs".to_string()];
            let scope = Scope::of(&patterns, &suffixes).expect("the patterns compile");
            collect(
                &Request {
                    root: self.root.to_string_lossy().into_owned(),
                    families: Vec::new(),
                    exclude: patterns.clone(),
                    suffixes: suffixes.clone(),
                    graph: false,
                },
                &scope,
            )
            .expect("the tree reads")
        }
    }

    impl Drop for Tree {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.root);
        }
    }

    /// Every directory fact one walk produced, keyed by the path it names.
    fn measured(inventory: &Inventory, catalogs: &BTreeSet<String>) -> BTreeMap<String, Value> {
        let packages = Packages::of(&inventory.documents);
        let roots = SourceRoots::of(&inventory.directories, &packages);
        directories(&inventory.directories, &roots, catalogs)
            .into_iter()
            .map(|fact| {
                let path = fact["span"]["path"]
                    .as_str()
                    .unwrap_or_default()
                    .to_string();
                (path, fact)
            })
            .collect()
    }

    #[test]
    fn a_directory_holding_nothing_is_reported_because_the_walk_met_it() {
        let tree = Tree::new("empty");
        tree.write("src/pkg/__init__.py", "")
            .directory("src/pkg/unused");

        let facts = measured(&tree.walk(&[]), &BTreeSet::new());

        assert_eq!(facts["src/pkg/unused"]["visible_entry_count"], 0);
        assert_eq!(facts["src/pkg/unused"]["is_ignored"], false);
        assert_eq!(facts["src/pkg/unused"]["is_retained"], false);
        assert_eq!(facts["src/pkg"]["visible_entry_count"], 2);
    }

    #[test]
    fn a_directory_of_siblings_is_one_fact_saying_how_many_rather_than_one_fact_each() {
        let tree = Tree::new("siblings");
        for name in ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"] {
            tree.write(&format!("services/{name}.py"), "value = 1\n");
        }
        tree.write("services/payments/charge.py", "value = 1\n");

        let inventory = tree.walk(&[]);
        let facts = measured(&inventory, &BTreeSet::new());

        assert_eq!(inventory.documents.len(), 7);
        assert_eq!(facts.len(), 3);
        assert_eq!(facts["services"]["direct_module_count"], 6);
        assert_eq!(facts["services"]["visible_entry_count"], 7);
        assert_eq!(facts["services/payments"]["direct_module_count"], 1);
    }

    #[test]
    fn depth_is_measured_below_the_source_root_rather_than_from_the_repository() {
        let tree = Tree::new("depth");
        tree.write("src/shop/__init__.py", "")
            .write("src/shop/orders/__init__.py", "")
            .write("src/shop/orders/commands/__init__.py", "")
            .write("kernel/src/lib.rs", "pub fn run() {}\n")
            .write("kernel/src/passes/mod.rs", "pub fn apply() {}\n");

        let facts = measured(&tree.walk(&[]), &BTreeSet::new());

        assert_eq!(facts["."]["source_depth"], 0);
        assert_eq!(facts["src"]["source_depth"], 0);
        assert_eq!(facts["src/shop/orders/commands"]["source_depth"], 3);
        assert_eq!(facts["kernel"]["source_depth"], 1);
        assert_eq!(facts["kernel/src"]["source_depth"], 0);
        assert_eq!(facts["kernel/src/passes"]["source_depth"], 1);
    }

    #[test]
    fn a_flat_layout_measures_depth_from_the_repository_root() {
        let tree = Tree::new("flat");
        tree.write("shop/__init__.py", "")
            .write("shop/orders/__init__.py", "");

        let facts = measured(&tree.walk(&[]), &BTreeSet::new());

        assert_eq!(facts["shop"]["source_depth"], 1);
        assert_eq!(facts["shop/orders"]["source_depth"], 2);
    }

    #[test]
    fn a_directory_holding_only_excluded_entries_reads_as_empty_and_is_never_entered() {
        let tree = Tree::new("excluded");
        tree.write("app/main.py", "value = 1\n")
            .write("app/generated/__pycache__/main.pyc", "")
            .write("target/debug/build/output.rs", "pub fn run() {}\n");

        let inventory = tree.walk(&["**/__pycache__/**", "**/target/**"]);
        let facts = measured(&inventory, &BTreeSet::new());

        assert_eq!(inventory.documents.len(), 1);
        assert_eq!(facts["app/generated"]["visible_entry_count"], 0);
        assert_eq!(facts["app/generated"]["is_ignored"], false);
        assert!(!facts.contains_key("target"));
        assert!(!facts.contains_key("target/debug"));
        assert!(!facts.contains_key("app/generated/__pycache__"));
    }

    #[test]
    fn a_placeholder_says_an_empty_directory_is_deliberate() {
        let tree = Tree::new("retained");
        tree.write("fixtures/.gitkeep", "").directory("leftover");

        let facts = measured(&tree.walk(&[]), &BTreeSet::new());

        assert_eq!(facts["fixtures"]["visible_entry_count"], 0);
        assert_eq!(facts["fixtures"]["is_retained"], true);
        assert_eq!(facts["leftover"]["visible_entry_count"], 0);
        assert_eq!(facts["leftover"]["is_retained"], false);
    }

    #[test]
    fn generated_output_is_skipped_without_anybody_asking_for_it() {
        let tree = Tree::new("generated");
        tree.write("src/app.py", "value = 1\n")
            .write(".svelte-kit/generated/root.py", "value = 1\n")
            .write(".next/server/page.py", "value = 1\n")
            .write(".wrangler/state/worker.py", "value = 1\n")
            .write("build/generated/output.py", "value = 1\n")
            .write("core/.build/_deps/vendor/lib.py", "value = 1\n")
            .write(".venv/lib/site-packages/pkg/mod.py", "value = 1\n");

        let inventory = tree.walk(&[]);
        let read: Vec<&str> = inventory
            .documents
            .iter()
            .map(|document| document.relative.as_str())
            .collect();

        // Two thirds of one real report was about files inside `.svelte-kit`, which no reader can
        // act on and no commit can change, so the frameworks MCMR fronts are skipped the way a
        // build tree already was.
        assert_eq!(read, vec!["src/app.py"]);
    }

    #[test]
    fn a_directory_a_person_edits_is_never_skipped_by_a_default() {
        let tree = Tree::new("edited");
        // Each of these is a word one of the skipped names contains or resembles, and every one
        // of them is a source directory somebody maintains.
        tree.write("venv/manager.py", "value = 1\n")
            .write("coverage/report.py", "value = 1\n")
            .write("src/output/writer.py", "value = 1\n")
            .write("src/next/step.py", "value = 1\n")
            .write("src/build_tools/plan.py", "value = 1\n");

        let inventory = tree.walk(&[]);

        assert_eq!(inventory.documents.len(), 5);
    }

    #[test]
    fn what_a_caller_excludes_is_added_to_the_defaults_rather_than_replacing_them() {
        let tree = Tree::new("added");
        tree.write("src/app.py", "value = 1\n")
            .write("src/legacy.py", "value = 1\n")
            .write("node_modules/left/index.py", "value = 1\n");

        let inventory = tree.walk(&["**/legacy.py"]);
        let read: Vec<&str> = inventory
            .documents
            .iter()
            .map(|document| document.relative.as_str())
            .collect();

        assert_eq!(read, vec!["src/app.py"]);
    }

    #[test]
    fn a_dotted_directory_is_reported_as_ignored_and_what_it_holds_is_not_described() {
        let tree = Tree::new("hidden");
        tree.directory(".cache/objects")
            .write(".cache/generated.py", "value = 1\n")
            .write("app/main.py", "value = 1\n");

        let inventory = tree.walk(&[]);
        let facts = measured(&inventory, &BTreeSet::new());

        assert_eq!(facts[".cache"]["is_ignored"], true);
        assert_eq!(facts[".cache"]["visible_entry_count"], 2);
        assert!(!facts.contains_key(".cache/objects"));
        assert_eq!(facts["."]["visible_entry_count"], 1);
        assert_eq!(inventory.documents.len(), 2);
    }

    #[test]
    fn a_directory_whose_every_module_declares_one_thing_is_a_catalog() {
        let declared = |path: &str, classes: u64, functions: u64, initializer: bool| {
            json!({
                "span": {"path": path},
                "class_count": classes,
                "function_count": functions,
                "is_package_initializer": initializer,
            })
        };

        let catalogs = definition_catalogs(&[
            declared("rules/r0001.py", 0, 1, false),
            declared("rules/r0002.py", 1, 0, false),
            declared("rules/__init__.py", 0, 0, true),
            declared("engine/core.py", 3, 2, false),
            declared("engine/one.py", 1, 0, false),
        ]);

        assert_eq!(catalogs, BTreeSet::from(["rules".to_string()]));
    }

    #[test]
    fn a_module_is_named_from_the_package_root_the_import_system_would_find() {
        let packages = Packages::of(&[
            document("packages/mcmr/src/mcmr/__init__.py"),
            document("packages/mcmr/src/mcmr/rules/__init__.py"),
        ]);

        assert_eq!(
            packages.module_name("packages/mcmr/src/mcmr/engine.py"),
            "mcmr.engine"
        );
        assert_eq!(
            packages.module_name("packages/mcmr/src/mcmr/rules/__init__.py"),
            "mcmr.rules"
        );
        assert_eq!(packages.module_name("scripts/deploy.py"), "deploy");
    }

    #[test]
    fn a_rust_module_is_named_from_the_directory_that_holds_its_crate_root() {
        let crates = Crates::of(&[
            document("packages/mcmr/kernel/src/main.rs"),
            document("tools/lint/src/lib.rs"),
        ]);

        assert_eq!(
            crates.module_name("packages/mcmr/kernel/src/graph.rs"),
            "kernel::graph"
        );
        assert_eq!(
            crates.module_name("packages/mcmr/kernel/src/rules/mod.rs"),
            "kernel::rules"
        );
        assert_eq!(
            crates.module_name("packages/mcmr/kernel/src/main.rs"),
            "kernel"
        );
        assert_eq!(crates.module_name("tools/lint/src/pass.rs"), "lint::pass");
    }

    #[test]
    fn suffix_matching_reads_the_whole_name() {
        let scope = Scope::of(&[], &[".py".to_string(), ".pyi".to_string()])
            .expect("the patterns compile");

        assert!(scope.holds("a/b.py"));
        assert!(scope.holds("a/b.pyi"));
        assert!(!scope.holds("a/b.python"));
    }
}
