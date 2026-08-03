use super::*;

#[test]
fn a_surface_names_what_it_republishes_and_how_far_it_reaches() {
    let facts = facts_for(
        concat!(
            "export * from './UserService';\n",
            "export { User } from '../../models/user';\n",
            "import { Held } from '../held';\n",
        ),
        FactFamily("ModuleSurfaceFact"),
    );

    assert_eq!(facts[0]["star_reexports"][0], "./UserService");
    assert_eq!(facts[0]["star_reexports"].as_array().unwrap().len(), 1);
    assert_eq!(facts[0]["deepest_relative_import"], 2);
    assert_eq!(facts[0]["deepest_relative_specifier"], "../../models/user");
}

#[test]
fn a_whole_small_project_produces_exactly_the_nodes_and_edges_written_out_by_hand() {
    let graph = graph_of(&[
        (
            "src/models.ts",
            "export interface Shape {\n  area: number;\n}\n\nexport class Circle implements Shape {\n  area = 1;\n}\n",
        ),
        (
            "src/main.ts",
            "import { Circle } from './models';\n\nexport function build(): Circle {\n  return new Circle();\n}\n",
        ),
    ]);

    assert_eq!(
        symbols(&graph),
        [
            "typescript:attribute:src/models.Circle.area",
            "typescript:attribute:src/models.Shape.area",
            "typescript:class:src/models.Circle",
            "typescript:class:src/models.Shape",
            "typescript:function:src/main.build",
            "typescript:module:src/main",
            "typescript:module:src/models",
        ]
    );
    assert_eq!(
        relations(&graph),
        [
            "path:file:src/main.ts Define typescript:module:src/main",
            "path:file:src/models.ts Define typescript:module:src/models",
            "typescript:class:src/models.Circle Define typescript:attribute:src/models.Circle.area",
            "typescript:class:src/models.Circle Inherit typescript:class:src/models.Shape",
            "typescript:class:src/models.Shape Define typescript:attribute:src/models.Shape.area",
            "typescript:function:src/main.build Instantiate typescript:class:src/models.Circle",
            "typescript:function:src/main.build Typed typescript:class:src/models.Circle",
            "typescript:module:src/main Access typescript:class:src/models.Circle",
            "typescript:module:src/main Define typescript:function:src/main.build",
            "typescript:module:src/main Import typescript:module:src/models",
            "typescript:module:src/models Define typescript:class:src/models.Circle",
            "typescript:module:src/models Define typescript:class:src/models.Shape",
        ]
    );
    assert!(
        graph
            .edges
            .iter()
            .all(|edge| edge.resolution == Resolution::Exact)
    );
}

#[test]
fn a_contract_is_an_interface_an_abstract_class_or_an_alias_and_never_an_enum() {
    let graph = graph_of(&[(
        "src/shapes.ts",
        "export interface Reader {\n  read(): string;\n}\n\nexport abstract class Shape {}\n\nexport type Named = { name: string };\n\nexport enum Mode {\n  Fast,\n}\n\nexport class Circle extends Shape {}\n",
    )]);
    let stated: Vec<(&str, bool)> = graph
        .nodes
        .iter()
        .filter(|node| node.kind == NodeKind::Class)
        .map(|node| (node.qualname.as_str(), node.is_abstract))
        .collect();

    assert_eq!(
        stated,
        [
            ("src/shapes.Circle", false),
            ("src/shapes.Mode", false),
            ("src/shapes.Named", true),
            ("src/shapes.Reader", true),
            ("src/shapes.Shape", true),
        ]
    );
}

#[test]
fn a_parameter_carries_how_it_binds_and_whether_a_caller_may_leave_it_out() {
    let graph = graph_of(&[(
        "src/run.ts",
        "export function run(first: string, second = 2, third?: number, ...rest: string[]) {\n  return first;\n}\n",
    )]);
    let mut stated: Vec<(&str, Option<ParameterKind>, bool, Option<usize>)> = graph
        .nodes
        .iter()
        .filter(|node| node.kind == NodeKind::Parameter)
        .map(|node| {
            (
                node.qualname.as_str(),
                node.parameter_kind,
                node.has_default,
                node.ordinal,
            )
        })
        .collect();
    stated.sort_by_key(|held| held.3);

    assert_eq!(
        stated,
        [
            (
                "src/run.run.first",
                Some(ParameterKind::PositionalOnly),
                false,
                Some(0)
            ),
            (
                "src/run.run.second",
                Some(ParameterKind::PositionalOnly),
                true,
                Some(1)
            ),
            (
                "src/run.run.third",
                Some(ParameterKind::PositionalOnly),
                true,
                Some(2)
            ),
            (
                "src/run.run.rest",
                Some(ParameterKind::VarPositional),
                false,
                Some(3)
            ),
        ]
    );
}

#[test]
fn a_destructured_position_declares_no_name_and_still_holds_its_place() {
    let graph = graph_of(&[(
        "src/run.ts",
        "export function run({ left, right }: Pair, total: number) {\n  return total;\n}\n",
    )]);
    let stated: Vec<(&str, Option<usize>)> = graph
        .nodes
        .iter()
        .filter(|node| node.kind == NodeKind::Parameter)
        .map(|node| (node.qualname.as_str(), node.ordinal))
        .collect();

    assert_eq!(stated, [("src/run.run.total", Some(1))]);
}

#[test]
fn visibility_reads_the_export_keyword_and_every_member_modifier() {
    let graph = graph_of(&[(
        "src/engine.ts",
        "export class Engine {\n  open = 1;\n  protected middle = 2;\n  private closed = 3;\n  #hidden = 4;\n}\n\nfunction helper() {}\n\nexport function shown() {}\n",
    )]);
    let mut stated: Vec<(&str, Visibility)> = graph
        .nodes
        .iter()
        .filter(|node| !node.id.starts_with("path:") && node.kind != NodeKind::Module)
        .map(|node| (node.qualname.as_str(), node.visibility))
        .collect();
    stated.sort_by_key(|held| held.0);

    assert_eq!(
        stated,
        [
            ("src/engine.Engine", Visibility::Public),
            ("src/engine.Engine.#hidden", Visibility::Private),
            ("src/engine.Engine.closed", Visibility::Private),
            ("src/engine.Engine.middle", Visibility::Protected),
            ("src/engine.Engine.open", Visibility::Public),
            ("src/engine.helper", Visibility::Internal),
            ("src/engine.shown", Visibility::Public),
        ]
    );
}

#[test]
fn a_name_published_by_a_later_export_statement_still_reads_as_public() {
    let graph = graph_of(&[(
        "src/engine.ts",
        "function helper() {}\n\nexport { helper };\n",
    )]);

    assert_eq!(
        node_of(&graph, "typescript:function:src/engine.helper").visibility,
        Visibility::Public
    );
}

#[test]
fn a_specifier_reaches_the_file_typescript_would_have_opened() {
    let graph = graph_of(&[
        (
            "src/main.ts",
            "import { helper } from './util';\nimport { thing } from './pack';\nimport { shape } from './shapes.js';\nimport { stated } from './ambient';\n",
        ),
        ("src/util.ts", "export const helper = 1;\n"),
        ("src/pack/index.ts", "export const thing = 1;\n"),
        ("src/shapes.ts", "export const shape = 1;\n"),
        ("src/ambient.d.ts", "export const stated = 1;\n"),
    ]);

    assert_eq!(
        reaching(&graph, EdgeKind::Import),
        [
            (
                "typescript:module:src/main",
                "typescript:module:src/ambient.d"
            ),
            (
                "typescript:module:src/main",
                "typescript:module:src/pack/index"
            ),
            ("typescript:module:src/main", "typescript:module:src/shapes"),
            ("typescript:module:src/main", "typescript:module:src/util"),
        ]
    );
}

#[test]
fn an_import_of_a_reexported_symbol_reaches_what_defines_it() {
    let graph = graph_of(&[
        (
            "src/index.ts",
            "export { rule } from './decorators';\nexport * from './helpers';\n",
        ),
        ("src/decorators.ts", "export function rule() {}\n"),
        ("src/helpers.ts", "export function assist() {}\n"),
        (
            "src/api.ts",
            "import { rule, assist } from './index';\n\nexport function run() {\n  return rule() + assist();\n}\n",
        ),
    ]);
    let reached: Vec<&str> = graph
        .edges
        .iter()
        .filter(|edge| edge.kind == EdgeKind::Import && edge.path == "src/api.ts")
        .map(|edge| edge.target.as_str())
        .collect();

    assert_eq!(
        reached,
        [
            "typescript:module:src/decorators",
            "typescript:module:src/helpers"
        ]
    );
    assert!(reaching(&graph, EdgeKind::Call).contains(&(
        "typescript:function:src/api.run",
        "typescript:function:src/decorators.rule"
    )));
}

#[test]
fn a_default_export_is_reached_under_whatever_name_the_importer_chose() {
    let graph = graph_of(&[
        ("src/widget.ts", "export default class Widget {}\n"),
        (
            "src/main.ts",
            "import Panel from './widget';\n\nexport function build() {\n  return new Panel();\n}\n",
        ),
    ]);

    assert!(reaching(&graph, EdgeKind::Instantiate).contains(&(
        "typescript:function:src/main.build",
        "typescript:class:src/widget.Widget"
    )));
    assert!(
        reaching(&graph, EdgeKind::Import)
            .contains(&("typescript:module:src/main", "typescript:module:src/widget"))
    );
}

#[test]
fn a_binding_whose_value_is_a_callable_is_declared_as_one() {
    let graph = graph_of(&[(
        "src/load.ts",
        "export const load = async (event: string) => event.length;\n",
    )]);
    let declared = node_of(&graph, "typescript:function:src/load.load");

    assert!(declared.asynchronous);
    assert_eq!(declared.visibility, Visibility::Public);
    assert_eq!(
        node_of(&graph, "typescript:parameter:src/load.load.event").annotation,
        Some("string".to_string())
    );
}

#[test]
fn a_receiver_written_as_this_reaches_the_member_of_its_own_class() {
    let graph = graph_of(&[(
        "src/engine.ts",
        "export class Engine {\n  limit = 1;\n\n  run() {\n    return this.size();\n  }\n\n  size() {\n    return this.limit;\n  }\n}\n",
    )]);

    assert!(reaching(&graph, EdgeKind::Call).contains(&(
        "typescript:method:src/engine.Engine.run",
        "typescript:method:src/engine.Engine.size"
    )));
    assert!(reaching(&graph, EdgeKind::Access).contains(&(
        "typescript:method:src/engine.Engine.size",
        "typescript:attribute:src/engine.Engine.limit"
    )));
}
