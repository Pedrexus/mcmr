use super::*;

#[test]
fn a_nested_gitignore_controls_only_the_tree_below_it() {
    let tree = Tree::new("nested-ignore");
    tree.write("generated.py", "value = 1\n")
        .write("service/.gitignore", "generated.py\n!kept/generated.py\n")
        .write("service/generated.py", "value = 1\n")
        .write("service/kept/generated.py", "value = 1\n");

    let inventory = tree.walk();
    let read: Vec<&str> = inventory
        .documents
        .iter()
        .map(|document| document.relative.as_str())
        .collect();

    assert_eq!(read, vec!["generated.py", "service/kept/generated.py"]);
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

    let inventory = tree.walk();

    assert_eq!(inventory.documents.len(), 5);
}

#[test]
fn every_gitignore_pattern_applies_to_the_same_walk() {
    let tree = Tree::new("added");
    tree.write(".gitignore", "node_modules/\nsrc/legacy.py\n")
        .write("src/app.py", "value = 1\n")
        .write("src/legacy.py", "value = 1\n")
        .write("node_modules/left/index.py", "value = 1\n");

    let inventory = tree.walk();
    let read: Vec<&str> = inventory
        .documents
        .iter()
        .map(|document| document.relative.as_str())
        .collect();

    assert_eq!(read, vec!["src/app.py"]);
}

#[test]
fn an_unignored_dotted_directory_and_its_contents_are_described() {
    let tree = Tree::new("hidden");
    tree.directory(".cache/objects")
        .write(".cache/generated.py", "value = 1\n")
        .write("app/main.py", "value = 1\n");

    let inventory = tree.walk();
    let facts = measured(&inventory, &BTreeSet::new());

    assert_eq!(facts[".cache"]["entry_count"], 2);
    assert!(facts.contains_key(".cache/objects"));
    assert_eq!(facts["."]["entry_count"], 2);
    assert_eq!(inventory.documents.len(), 2);
}

#[test]
fn git_administration_is_not_source_but_an_owned_dotted_directory_is() {
    let tree = Tree::new("git-boundary");
    tree.directory(".git/refs/tags")
        .write(".git/hooks/check.py", "value = 1\n")
        .write(".hooks/check.py", "value = 1\n");

    let inventory = tree.walk();
    let facts = measured(&inventory, &BTreeSet::new());

    assert_eq!(inventory.documents.len(), 1);
    assert_eq!(inventory.documents[0].relative, ".hooks/check.py");
    assert!(!facts.contains_key(".git"));
    assert!(facts.contains_key(".hooks"));
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
        document("packages/mcmr/src/api/mcmr/__init__.py"),
        document("packages/mcmr/src/rules/mcmr/rules/writing/prose.py"),
    ]);

    assert_eq!(
        packages.module_name("packages/mcmr/src/api/mcmr/engine.py"),
        "mcmr.engine"
    );
    assert_eq!(
        packages.module_name("packages/mcmr/src/rules/mcmr/rules/writing/prose.py"),
        "mcmr.rules.writing.prose"
    );
    assert_eq!(packages.module_name("scripts/deploy.py"), "scripts.deploy");
    assert_eq!(packages.module_name("tests/oracle.py"), "tests.oracle");
    assert_eq!(
        packages.module_name("packages/mcmr/src/api/mcmr/kernel_tables.pyi"),
        "mcmr.kernel_tables"
    );
}

#[test]
fn a_package_root_does_not_claim_a_sibling_with_the_same_textual_prefix() {
    let packages = Packages::of(&[document("src/app/__init__.py")]);

    assert_eq!(packages.module_name("src2/run.py"), "src2.run");
}

#[test]
fn a_nested_regular_package_below_a_namespace_keeps_the_outer_package_root() {
    let packages = Packages::of(&[
        document("src/mcmr/__init__.py"),
        document("src/mcmr/rules/python/contextual/__init__.py"),
        document("src/mcmr/rules/python/contextual/interfaces/r1001.py"),
    ]);

    assert_eq!(
        packages.module_name("src/mcmr/rules/python/contextual/interfaces/r1001.py"),
        "mcmr.rules.python.contextual.interfaces.r1001"
    );
}

#[test]
fn a_split_namespace_is_not_hidden_by_a_regular_package_below_it() {
    let packages = Packages::of(&[
        document("src/api/mcmr/__init__.py"),
        document("src/rules/mcmr/rules/general/deterministic/coupling/__init__.py"),
        document("src/rules/mcmr/rules/general/deterministic/architecture/r0010.py"),
    ]);

    assert_eq!(
        packages.module_name("src/rules/mcmr/rules/general/deterministic/architecture/r0010.py"),
        "mcmr.rules.general.deterministic.architecture.r0010"
    );
}

#[test]
fn fully_regular_split_namespace_branches_keep_the_shared_outer_package() {
    let packages = Packages::of(&[
        document("src/api/mcmr/__init__.py"),
        document("src/rules/mcmr/rules/general/__init__.py"),
        document("src/rules/mcmr/rules/general/architecture/r0010.py"),
        document("src/rules/mcmr/rules/python/__init__.py"),
        document("src/rules/mcmr/rules/python/imports/r0005.py"),
    ]);

    assert_eq!(
        packages.module_name("src/rules/mcmr/rules/general/architecture/r0010.py"),
        "mcmr.rules.general.architecture.r0010"
    );
    assert_eq!(
        packages.module_name("src/rules/mcmr/rules/python/imports/r0005.py"),
        "mcmr.rules.python.imports.r0005"
    );
}

#[test]
fn a_rust_module_is_named_from_the_directory_that_holds_its_crate_root() {
    let crates = Crates::of(
        Path::new("repository"),
        &[
            document("packages/mcmr/kernel/src/main.rs"),
            document("tools/lint/src/lib.rs"),
        ],
    );

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
    assert_eq!(crates.module_name("scripts/check.rs"), "scripts::check");
}

#[test]
fn a_crate_at_the_discovery_root_is_named_without_panicking() {
    let crates = Crates::of(Path::new("/workspace/core"), &[document("src/lib.rs")]);

    assert_eq!(crates.module_name("src/lib.rs"), "core");
    assert_eq!(crates.module_name("src/rules/mod.rs"), "core::rules");
}

#[test]
fn suffix_matching_reads_the_whole_name() {
    let scope = Scope::of(Path::new("."), &[".py".to_string(), ".pyi".to_string()]);

    assert!(scope.holds("a/b.py"));
    assert!(scope.holds("a/b.pyi"));
    assert!(!scope.holds("a/b.python"));
}

#[test]
fn a_source_directory_may_hold_nested_language_roots() {
    let workspace = Tree::new("parent-ignore");
    workspace
        .write(".gitignore", "core\nbindings\n")
        .write("repository/.gitignore", "target/\n")
        .write("repository/src/core/src/lib.rs", "pub fn run() {}\n")
        .write("repository/src/bindings/src/lib.rs", "pub fn bind() {}\n");
    let root = workspace.root.join("repository");
    let scope = Scope::of(&root, &[".rs".to_string()]);

    assert!(!scope.excludes_directory("src/core"));
    assert!(!scope.excludes_directory("src/bindings"));
    assert!(scope.holds("src/core/src/lib.rs"));
    assert!(scope.holds("src/bindings/src/lib.rs"));
}
