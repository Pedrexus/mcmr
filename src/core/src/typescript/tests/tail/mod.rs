use super::*;

#[test]
fn a_package_this_repository_installs_is_a_dependency_rather_than_a_gap() {
    let graph = graph_of(&[(
        "src/schema.ts",
        "import { z } from 'zod';\nimport type { Handle } from '@sveltejs/kit';\n\nexport const shape = z.object();\n",
    )]);
    let outside: Vec<(&str, &str)> = graph
        .nodes
        .iter()
        .filter(|node| {
            matches!(
                node.kind,
                NodeKind::ExternalModule | NodeKind::ExternalSymbol
            )
        })
        .map(|node| (node.id.as_str(), node.qualname.as_str()))
        .collect();

    assert_eq!(
        outside,
        [
            ("typescript:external-module:@sveltejs/kit", "@sveltejs/kit"),
            ("typescript:external-module:zod", "zod"),
            (
                "typescript:external-symbol:@sveltejs/kit.Handle",
                "@sveltejs/kit.Handle"
            ),
            ("typescript:external-symbol:zod.z", "zod.z"),
            ("typescript:external-symbol:zod.z.object", "zod.z.object"),
        ]
    );
    assert!(
        graph
            .edges
            .iter()
            .filter(|edge| edge.target.contains(":external-"))
            .all(|edge| edge.resolution == Resolution::External)
    );
}

#[test]
fn what_cannot_be_settled_stays_visible_rather_than_being_dropped() {
    let graph = graph_of(&[(
        "src/main.ts",
        "import Button from './Button.svelte';\n\nexport function run(handler) {\n  return handler(Button);\n}\n",
    )]);
    let gaps: Vec<&str> = graph
        .nodes
        .iter()
        .filter(|node| node.kind == NodeKind::UnresolvedSymbol)
        .map(|node| node.qualname.as_str())
        .collect();

    assert_eq!(gaps, ["src/main::handler", "src/main::src/Button.svelte"]);
    assert!(
        graph
            .edges
            .iter()
            .filter(|edge| edge.target.contains(":unresolved-symbol:"))
            .all(|edge| edge.resolution == Resolution::Unresolved)
    );
}

#[test]
fn a_type_parameter_is_a_binder_rather_than_a_dependency_on_anything() {
    let graph = graph_of(&[(
        "src/box.ts",
        "export interface Held {\n  size: number;\n}\n\nexport function unwrap<T extends Held>(held: T): T {\n  return held;\n}\n",
    )]);

    assert!(
        graph
            .nodes
            .iter()
            .all(|node| node.kind != NodeKind::UnresolvedSymbol)
    );
    assert!(reaching(&graph, EdgeKind::Typed).contains(&(
        "typescript:function:src/box.unwrap",
        "typescript:class:src/box.Held"
    )));
}

#[test]
fn a_utility_type_the_language_declares_is_outside_this_repository() {
    let graph = graph_of(&[(
        "src/table.ts",
        "export interface Row {\n  id: string;\n}\n\nexport type Table = Record<string, Row>;\n",
    )]);
    let outside: Vec<&str> = graph
        .nodes
        .iter()
        .filter(|node| node.kind == NodeKind::ExternalSymbol)
        .map(|node| node.qualname.as_str())
        .collect();

    assert_eq!(outside, ["globalThis.Record"]);
}

#[test]
fn a_constructor_parameter_that_carries_a_modifier_declares_a_field_as_well() {
    let graph = graph_of(&[(
        "src/engine.ts",
        "export class Engine {\n  constructor(private readonly limit: number, plain: number) {\n    this.total = plain;\n  }\n}\n",
    )]);
    let held: Vec<(&str, Visibility)> = graph
        .nodes
        .iter()
        .filter(|node| node.kind == NodeKind::Attribute)
        .map(|node| (node.qualname.as_str(), node.visibility))
        .collect();

    assert_eq!(
        held,
        [
            ("src/engine.Engine.limit", Visibility::Private),
            ("src/engine.Engine.total", Visibility::Public),
        ]
    );
}

#[test]
fn a_configured_alias_reaches_the_module_the_mapping_names() {
    let root = std::env::temp_dir().join(format!("mcmr-tsconfig-{}", std::process::id()));
    std::fs::create_dir_all(root.join("generated")).expect("the temporary root is writable");
    std::fs::write(
            root.join("tsconfig.json"),
            "{\n  // the framework writes the mapping\n  \"extends\": \"./generated/tsconfig.json\",\n  \"compilerOptions\": { \"strict\": true },\n}\n",
        )
        .expect("the file is writable");
    std::fs::write(
            root.join("generated/tsconfig.json"),
            "{\"compilerOptions\": {\"paths\": {\"$lib\": [\"../src/lib\"], \"$lib/*\": [\"../src/lib/*\"]}}}",
        )
        .expect("the file is writable");
    let documents = [
            Document {
                relative: "src/lib/models.ts".to_string(),
                source: "export class User {}\n".to_string(),
            },
            Document {
                relative: "src/lib/index.ts".to_string(),
                source: "export const version = 1;\n".to_string(),
            },
            Document {
                relative: "src/routes/page.ts".to_string(),
                source: "import { User } from '$lib/models';\nimport { version } from '$lib';\nimport { missing } from '$lib/generated/runtime';\n".to_string(),
            },
        ];
    let graph =
        crate::graph::build(&root.to_string_lossy(), &documents).expect("the graph builds");
    std::fs::remove_dir_all(&root).expect("the temporary root is removable");
    let reached: Vec<&str> = graph
        .edges
        .iter()
        .filter(|edge| edge.kind == EdgeKind::Import)
        .map(|edge| edge.target.as_str())
        .collect();

    assert_eq!(
        reached,
        [
            "typescript:module:src/lib/models",
            "typescript:module:src/lib/index",
            "typescript:unresolved-symbol:src/routes/page::src/lib/generated/runtime",
        ]
    );
}

#[test]
fn a_relative_import_beyond_the_repository_root_stays_unresolved() {
    let graph = graph_of(&[
        (
            "src/main.ts",
            "import { User } from '../../models';\nexport const held = User;\n",
        ),
        ("models.ts", "export class User {}\n"),
    ]);

    assert!(graph.edges.iter().all(|edge| {
        edge.source != "typescript:module:src/main" || edge.target != "typescript:module:models"
    }));
    assert!(
        graph
            .nodes
            .iter()
            .any(|node| node.kind == NodeKind::UnresolvedSymbol
                && node.qualname == "src/main::../models")
    );
}

#[test]
fn a_broken_typescript_configuration_fails_graph_construction() {
    let root = std::env::temp_dir().join(format!("mcmr-tsconfig-invalid-{}", std::process::id()));
    std::fs::create_dir_all(&root).expect("the temporary root is writable");
    std::fs::write(root.join("tsconfig.json"), "{ invalid").expect("the file is writable");
    let documents = [Document {
        relative: "src/main.ts".to_string(),
        source: "export const value = 1;\n".to_string(),
    }];

    let failure = crate::graph::build(&root.to_string_lossy(), &documents)
        .expect_err("invalid TypeScript configuration must fail");

    assert!(failure.contains("tsconfig.json is not valid JSON"));
    std::fs::remove_dir_all(&root).expect("the temporary root is removable");
}

#[test]
fn a_typescript_configuration_path_that_is_not_a_file_fails() {
    let root =
        std::env::temp_dir().join(format!("mcmr-tsconfig-directory-{}", std::process::id()));
    std::fs::create_dir_all(root.join("tsconfig.json")).expect("the temporary root is writable");
    let documents = [Document {
        relative: "src/main.ts".to_string(),
        source: "export const value = 1;\n".to_string(),
    }];

    let failure = crate::graph::build(&root.to_string_lossy(), &documents)
        .expect_err("a directory cannot stand in for configuration");

    assert!(failure.contains("tsconfig.json could not be read"));
    std::fs::remove_dir_all(&root).expect("the temporary root is removable");
}

#[test]
fn a_path_mapping_cannot_hold_an_empty_target_list() {
    let root =
        std::env::temp_dir().join(format!("mcmr-tsconfig-empty-target-{}", std::process::id()));
    std::fs::create_dir_all(&root).expect("the temporary root is writable");
    std::fs::write(
        root.join("tsconfig.json"),
        "{\"compilerOptions\": {\"paths\": {\"$lib/*\": []}}}",
    )
    .expect("the file is writable");

    let ignored = crate::discovery::Scope::of(&root, &[]);
    let failure = mappings_at(&root, "", &ignored).expect_err("an empty mapping must fail");

    assert!(failure.contains("must not be empty"));
    std::fs::remove_dir_all(&root).expect("the temporary root is removable");
}

#[test]
fn a_circular_extends_chain_cannot_yield_partial_mappings() {
    let root = std::env::temp_dir().join(format!("mcmr-tsconfig-cycle-{}", std::process::id()));
    std::fs::create_dir_all(&root).expect("the temporary root is writable");
    std::fs::write(
        root.join("tsconfig.json"),
        "{\"extends\": \"./tsconfig.json\"}",
    )
    .expect("the file is writable");

    let failure = Specifiers::of(&root.to_string_lossy(), BTreeSet::from(["src/main".into()]))
        .expect_err("a circular configuration must fail");

    assert!(failure.contains("circular TypeScript extends chain"));
    std::fs::remove_dir_all(&root).expect("the temporary root is removable");
}

#[test]
fn an_ignored_extends_target_does_not_escape_the_discovery_scope() {
    let root = std::env::temp_dir().join(format!("mcmr-tsconfig-ignored-{}", std::process::id()));
    std::fs::create_dir_all(root.join("src/lib")).expect("the temporary root is writable");
    std::fs::write(root.join(".gitignore"), "generated/\n")
        .expect("the ignore contract is writable");
    std::fs::write(
            root.join("tsconfig.json"),
            "{\"extends\": \"./generated/tsconfig.json\", \"compilerOptions\": {\"paths\": {\"$lib/*\": [\"src/lib/*\"]}}}",
        )
        .expect("the configuration is writable");
    let documents = [
        Document {
            relative: "src/lib/model.ts".to_string(),
            source: "export class Model {}\n".to_string(),
        },
        Document {
            relative: "src/page.ts".to_string(),
            source: "import { Model } from '$lib/model';\nexport const value = Model;\n"
                .to_string(),
        },
    ];

    let graph =
        crate::graph::build(&root.to_string_lossy(), &documents).expect("the graph builds");

    assert!(graph.edges.iter().any(|edge| {
        edge.kind == EdgeKind::Import && edge.target == "typescript:module:src/lib/model"
    }));
    std::fs::remove_dir_all(&root).expect("the temporary root is removable");
}

#[test]
fn an_extends_chain_cannot_read_outside_the_repository() {
    let root = std::env::temp_dir().join(format!("mcmr-tsconfig-escape-{}", std::process::id()));
    std::fs::create_dir_all(&root).expect("the temporary root is writable");
    std::fs::write(
        root.join("tsconfig.json"),
        "{\"extends\": \"../outside.json\"}",
    )
    .expect("the file is writable");

    let failure = Specifiers::of(&root.to_string_lossy(), BTreeSet::from(["src/main".into()]))
        .expect_err("configuration must stay inside the repository");

    assert!(failure.contains("leaves the repository"));
    std::fs::remove_dir_all(&root).expect("the temporary root is removable");
}

#[test]
fn a_configuration_reads_through_the_comments_and_commas_json_forbids() {
    let read: Value = parse_config(
        "{\n  // a line comment\n  \"paths\": {\n    /* a block comment */\n    \"$lib/*\": [\"../src/lib/*\"],\n  },\n  \"note\": \"http://not-a-comment\",\n}\n",
    )
    .expect("JSONC must parse");

    assert_eq!(read["paths"]["$lib/*"][0], "../src/lib/*");
    assert_eq!(read["note"], "http://not-a-comment");
}

#[test]
fn a_specifier_is_read_as_a_path_a_mapping_or_the_package_it_names() {
    let specifiers = Specifiers::of(
        "",
        BTreeSet::from(["src/lib/models".to_string(), "src/pack/index".to_string()]),
    )
    .expect("the configuration is valid");

    assert_eq!(
        specifiers.locate(WrittenSpecifier {
            from: "src/main.ts",
            value: "./lib/models",
        }),
        Located::Module("src/lib/models".to_string())
    );
    assert_eq!(
        specifiers.locate(WrittenSpecifier {
            from: "src/lib/one.ts",
            value: "../pack",
        }),
        Located::Module("src/pack/index".to_string())
    );
    assert_eq!(
        specifiers.locate(WrittenSpecifier {
            from: "src/main.ts",
            value: "@scope/name/deep",
        }),
        Located::Package("@scope/name".to_string())
    );
    assert_eq!(
        specifiers.locate(WrittenSpecifier {
            from: "src/main.ts",
            value: "zod",
        }),
        Located::Package("zod".to_string())
    );
    assert_eq!(
        specifiers.locate(WrittenSpecifier {
            from: "src/main.ts",
            value: "./nowhere",
        }),
        Located::Unsettled("src/nowhere".to_string())
    );
}
