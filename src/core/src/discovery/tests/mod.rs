use super::*;
use std::sync::atomic::{AtomicUsize, Ordering};
mod ignored;

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
        crate::test_support::remove_directory(&root);
        std::fs::create_dir_all(&root).expect("the temporary root is writable");
        Self { root }
    }

    fn directory(&self, relative: &str) -> &Self {
        std::fs::create_dir_all(self.root.join(relative)).expect("the temporary root is writable");
        self
    }

    fn walk(&self) -> Inventory {
        self.walk_result().expect("the tree reads")
    }

    fn walk_result(&self) -> Result<Inventory, String> {
        let suffixes = vec![".py".to_string(), ".rs".to_string()];
        let scope = Scope::of(&self.root, &suffixes);
        collect(
            &Request {
                root: self.root.to_string_lossy().into_owned(),
                families: Vec::new(),
                suffixes: suffixes.clone(),
                graph: false,
                stream: false,
                fingerprint_only: false,
                python_standard_library: Vec::new(),
            },
            &scope,
        )
    }

    fn write(&self, relative: &str, source: &str) -> &Self {
        let path = self.root.join(relative);
        std::fs::create_dir_all(path.parent().expect("a written file sits in a directory"))
            .expect("the temporary root is writable");
        std::fs::write(path, source).expect("the temporary root is writable");
        self
    }
}

impl Drop for Tree {
    fn drop(&mut self) {
        crate::test_support::remove_directory(&self.root);
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

    let facts = measured(&tree.walk(), &BTreeSet::new());

    assert_eq!(facts["src/pkg/unused"]["entry_count"], 0);
    assert_eq!(facts["src/pkg"]["entry_count"], 2);
    assert_eq!(facts["src/pkg"]["direct_file_count"], 0);
    assert_eq!(facts["src/pkg"]["direct_directory_count"], 1);
    assert_eq!(facts["src/pkg"]["only_child_directory"], "unused");
    assert_eq!(facts["src/pkg"]["direct_module_count"], 0);
}

#[test]
fn a_directory_of_siblings_is_one_fact_saying_how_many_rather_than_one_fact_each() {
    let tree = Tree::new("siblings");
    for name in ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"] {
        tree.write(&format!("services/{name}.py"), "value = 1\n");
    }
    tree.write("services/payments/charge.py", "value = 1\n");

    let inventory = tree.walk();
    let facts = measured(&inventory, &BTreeSet::new());

    assert_eq!(inventory.documents.len(), 7);
    assert_eq!(facts.len(), 3);
    assert_eq!(facts["services"]["direct_module_count"], 6);
    assert_eq!(facts["services"]["direct_file_count"], 6);
    assert_eq!(facts["services"]["direct_directory_count"], 1);
    assert_eq!(facts["services"]["only_child_directory"], "payments");
    assert_eq!(facts["services"]["entry_count"], 7);
    assert_eq!(facts["services/payments"]["direct_module_count"], 1);
}

#[test]
fn guidance_is_read_separately_without_becoming_a_source_module() {
    let tree = Tree::new("guidance");
    tree.write("src/app.py", "value = 1\n")
        .write("README.md", "Run `chefe run test`.\n")
        .write("docs/ignored.txt", "not source\n");

    let inventory = tree.walk();
    let facts = measured(&inventory, &BTreeSet::new());
    let guides = inventory
        .guides
        .iter()
        .map(|document| document.relative.as_str())
        .collect::<Vec<_>>();

    assert_eq!(inventory.documents.len(), 1);
    assert_eq!(guides, vec!["README.md", "docs/ignored.txt"]);
    assert_eq!(facts["."]["direct_module_count"], 0);
    assert_eq!(facts["docs"]["direct_module_count"], 0);
    assert_eq!(facts["src"]["direct_module_count"], 1);
}

#[test]
fn depth_is_measured_below_the_source_root_rather_than_from_the_repository() {
    let tree = Tree::new("depth");
    tree.write("src/shop/__init__.py", "")
        .write("src/shop/orders/__init__.py", "")
        .write("src/shop/orders/commands/__init__.py", "")
        .write("kernel/src/lib.rs", "pub fn run() {}\n")
        .write("kernel/src/passes/mod.rs", "pub fn apply() {}\n");

    let facts = measured(&tree.walk(), &BTreeSet::new());

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

    let facts = measured(&tree.walk(), &BTreeSet::new());

    assert_eq!(facts["shop"]["source_depth"], 1);
    assert_eq!(facts["shop/orders"]["source_depth"], 2);
}

#[test]
fn a_directory_holding_only_excluded_entries_reads_as_empty_and_is_never_entered() {
    let tree = Tree::new("excluded");
    tree.write(".gitignore", "__pycache__/\ntarget/\n")
        .write("app/main.py", "value = 1\n")
        .write("app/generated/__pycache__/main.pyc", "")
        .write("target/debug/build/output.rs", "pub fn run() {}\n");

    let inventory = tree.walk();
    let facts = measured(&inventory, &BTreeSet::new());

    assert_eq!(inventory.documents.len(), 1);
    assert_eq!(facts["app/generated"]["entry_count"], 0);
    assert!(!facts.contains_key("target"));
    assert!(!facts.contains_key("target/debug"));
    assert!(!facts.contains_key("app/generated/__pycache__"));
}

#[test]
fn a_placeholder_is_an_ordinary_unignored_entry() {
    let tree = Tree::new("retained");
    tree.write("fixtures/.gitkeep", "").directory("leftover");

    let facts = measured(&tree.walk(), &BTreeSet::new());

    assert_eq!(facts["fixtures"]["entry_count"], 1);
    assert_eq!(facts["leftover"]["entry_count"], 0);
}

#[test]
fn git_ignored_output_is_skipped_without_anybody_asking_for_it() {
    let tree = Tree::new("generated");
    tree.write(
        ".gitignore",
        ".svelte-kit/\n.next/\n.wrangler/\nbuild/\n.build/\n.venv/\n.lake/\n",
    )
    .write("src/app.py", "value = 1\n")
    .write(".svelte-kit/generated/root.py", "value = 1\n")
    .write(".next/server/page.py", "value = 1\n")
    .write(".wrangler/state/worker.py", "value = 1\n")
    .write(
        "research/.lake/packages/mathlib/generator.py",
        "value = 1\n",
    )
    .write("build/generated/output.py", "value = 1\n")
    .write("core/.build/_deps/vendor/lib.py", "value = 1\n")
    .write(".venv/lib/site-packages/pkg/mod.py", "value = 1\n");

    let inventory = tree.walk();
    let read: Vec<&str> = inventory
        .documents
        .iter()
        .map(|document| document.relative.as_str())
        .collect();

    assert_eq!(read, vec!["src/app.py"]);
}

#[test]
fn a_tool_directory_is_source_when_the_repository_does_not_ignore_it() {
    let tree = Tree::new("owned-tool-directory");
    tree.write("build/generator.py", "value = 1\n")
        .write(".venv/bootstrap.py", "value = 1\n");

    let inventory = tree.walk();
    let read: Vec<&str> = inventory
        .documents
        .iter()
        .map(|document| document.relative.as_str())
        .collect();

    assert_eq!(read, vec![".venv/bootstrap.py", "build/generator.py"]);
}

#[test]
fn an_unreadable_source_fails_instead_of_disappearing_from_discovery() {
    let tree = Tree::new("non-utf8");
    std::fs::write(tree.root.join("broken.py"), [0xff, 0xfe])
        .expect("the temporary source is writable");

    let failure = match tree.walk_result() {
        Ok(_) => panic!("non-UTF-8 source must fail discovery"),
        Err(failure) => failure,
    };

    assert!(failure.contains("broken.py could not be read as UTF-8"));
}

#[cfg(unix)]
#[test]
fn a_non_utf8_path_fails_instead_of_becoming_a_different_path() {
    use std::os::unix::ffi::OsStringExt;

    let tree = Tree::new("non-utf8-path");
    let name = std::ffi::OsString::from_vec(vec![b'b', 0xff, b'.', b'p', b'y']);
    std::fs::write(tree.root.join(name), b"value = 1\n")
        .expect("the temporary source is writable");

    let failure = match tree.walk_result() {
        Ok(_) => panic!("a non-UTF-8 path must fail discovery"),
        Err(failure) => failure,
    };

    assert!(failure.contains("is not valid UTF-8"));
}
