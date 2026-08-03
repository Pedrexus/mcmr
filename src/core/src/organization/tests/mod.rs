use super::*;

fn organization(sources: &[(&str, &str)]) -> Organization {
    let documents = sources
        .iter()
        .map(|(path, source)| Document {
            relative: (*path).to_string(),
            source: (*source).to_string(),
        })
        .collect::<Vec<_>>();
    let packages = Packages::of(&documents);
    Organization::of(&documents, &packages)
}

#[test]
fn enum_placement_uses_definitions_and_cross_module_imports() {
    let organization = organization(&[
        ("shop/__init__.py", ""),
        ("shop/orders/__init__.py", ""),
        (
            "shop/orders/status.py",
            "from enum import Enum\n\nclass State(Enum):\n    OPEN = 'open'\n\nclass Local(Enum):\n    HELD = 'held'\n",
        ),
        ("shop/orders/service.py", "from .status import State\n"),
        (
            "shop/billing/invoice.py",
            "from shop.orders.status import State\n",
        ),
        (
            "shop/enums/mixed.py",
            "from enum import Enum\n\nclass A(Enum):\n    A = 1\n\nclass Helper:\n    pass\n",
        ),
    ]);

    let fact = organization.enum_fact();

    assert_eq!(fact["scopes"][0]["destination"], "shop/enums.py");
    assert_eq!(fact["scopes"][0]["reused_enum_count"], 1);
    assert_eq!(fact["scopes"][0]["cross_module_import_count"], 2);
    assert_eq!(fact["files"][0]["top_level_class_count"], 2);
    assert_eq!(fact["files"][0]["enum_class_count"], 1);
}

#[test]
fn typing_placement_recognizes_aliases_factories_and_contracts() {
    let organization = organization(&[
        ("shop/__init__.py", ""),
        (
            "shop/orders/types.py",
            "from typing import NewType, Protocol, TypeAlias\n\nOrderId = NewType('OrderId', int)\nPayload: TypeAlias = dict[str, str]\ntype Price = int\nclass Reader(Protocol):\n    pass\n",
        ),
        (
            "shop/orders/service.py",
            "from .types import OrderId, Payload, Price, Reader\n",
        ),
    ]);

    let fact = organization.typing_fact();

    assert_eq!(fact["typing_scopes"][0]["path"], "shop/orders");
    assert_eq!(
        fact["typing_scopes"][0]["definitions"]
            .as_array()
            .unwrap()
            .len(),
        4
    );
    assert_eq!(
        fact["typing_scopes"][0]["reused_definitions"]
            .as_array()
            .unwrap()
            .len(),
        4
    );
    let import_count = fact["typing_scopes"][0]["reused_definitions"]
        .as_array()
        .unwrap()
        .iter()
        .map(|definition| definition["importing_spans"].as_array().unwrap().len())
        .sum::<usize>();
    assert_eq!(import_count, 4);
}

#[test]
fn nested_placement_scopes_never_count_one_definition_twice() {
    let organization = organization(&[
        ("shop/__init__.py", ""),
        ("shop/orders/__init__.py", ""),
        (
            "shop/orders/types.py",
            "type Local = int\ntype Shared = str\ntype Idle = bytes\n",
        ),
        ("shop/orders/service.py", "from .types import Local\n"),
        ("shop/billing.py", "from shop.orders.types import Shared\n"),
    ]);

    let fact = organization.typing_fact();
    let scopes = fact["typing_scopes"].as_array().expect("typing scopes");
    let root = scopes
        .iter()
        .find(|scope| scope["path"] == "shop")
        .expect("cross-package scope");
    let orders = scopes
        .iter()
        .find(|scope| scope["path"] == "shop/orders")
        .expect("orders scope");

    let root_names = root["definitions"]
        .as_array()
        .unwrap()
        .iter()
        .map(|definition| definition["name"].as_str().unwrap())
        .collect::<Vec<_>>();
    let order_names = orders["definitions"]
        .as_array()
        .unwrap()
        .iter()
        .map(|definition| definition["name"].as_str().unwrap())
        .collect::<Vec<_>>();
    assert_eq!(root_names, vec!["Shared"]);
    assert_eq!(order_names, vec!["Local", "Idle"]);
}

#[test]
fn test_consumers_do_not_move_a_production_contract_out_of_its_package() {
    let organization = organization(&[
        ("shop/__init__.py", ""),
        ("shop/types.py", "type OrderId = int\n"),
        ("tests/support.py", "from shop.types import OrderId\n"),
    ]);

    let fact = organization.typing_fact();

    assert!(fact["typing_scopes"].as_array().unwrap().is_empty());
}

#[test]
fn root_test_typings_and_root_production_typings_stay_in_separate_scopes() {
    let organization = organization(&[
        ("domain.py", "type DomainId = int\n"),
        ("service.py", "from domain import DomainId\n"),
        ("test_types.py", "type FixtureId = int\n"),
        ("test_service.py", "from test_types import FixtureId\n"),
    ]);

    let fact = organization.typing_fact();
    let scopes = fact["typing_scopes"].as_array().expect("typing scopes");

    assert_eq!(scopes.len(), 2);
    assert_eq!(scopes[0]["definitions"][0]["name"], "DomainId");
    assert_eq!(scopes[1]["definitions"][0]["name"], "FixtureId");
}
