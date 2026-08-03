use super::*;

fn enriched(sources: &[(&str, &str)]) -> Vec<Value> {
    let mut facts = extracted(sources);
    facts
        .remove("ClassFact")
        .unwrap_or_default()
        .into_iter()
        .flat_map(|fact| {
            fact["classes"]
                .as_array()
                .cloned()
                .unwrap_or_default()
                .into_iter()
        })
        .collect()
}

fn extracted(sources: &[(&str, &str)]) -> BTreeMap<String, Vec<Value>> {
    let documents: Vec<Document> = sources
        .iter()
        .map(|(relative, source)| Document {
            relative: (*relative).to_string(),
            source: (*source).to_string(),
        })
        .collect();
    let packages = Packages::of(&documents);
    let mut facts: BTreeMap<String, Vec<Value>> = BTreeMap::from([
        ("ClassFact".to_string(), Vec::new()),
        ("FunctionFact".to_string(), Vec::new()),
    ]);
    let mut stats = crate::protocol::Stats::default();
    for document in &documents {
        crate::python::extract(document, &packages, &mut facts, &mut stats);
    }
    enrich(&mut facts, &documents, &packages);
    facts
}

fn class(classes: &[Value], name: impl AsRef<str>) -> &Value {
    classes
        .iter()
        .find(|held| held["name"] == name.as_ref())
        .expect("the class is declared")
}

#[test]
fn a_base_kept_only_for_one_subclass_states_every_half_of_that_proof() {
    let classes = enriched(&[
        ("shop/__init__.py", ""),
        (
            "shop/support.py",
            "class ServiceSupport:\n    def normalize(self, value):\n        return value.strip()\n",
        ),
        (
            "shop/service.py",
            "from .support import ServiceSupport\n\n\nclass Service(ServiceSupport):\n    pass\n",
        ),
    ]);
    let base = class(&classes, "ServiceSupport");

    assert_eq!(base["direct_subclasses"], json!(["Service"]));
    assert_eq!(base["descendant_count"], 1);
    assert_eq!(base["is_instantiated"], false);
    assert_eq!(base["is_exported"], false);
    assert_eq!(base["only_cross_module_reference_is_subclass"], true);
    assert_eq!(
        class(&classes, "Service")["base_is_removable_overlap"],
        true
    );
}

#[test]
fn a_subclass_imported_through_an_explicit_package_export_reaches_its_base() {
    let classes = enriched(&[
        ("shop/__init__.py", ""),
        (
            "shop/contracts/__init__.py",
            "from .source import ServiceBase\n\n__all__ = ['ServiceBase']\n",
        ),
        ("shop/contracts/source.py", "class ServiceBase:\n    pass\n"),
        (
            "shop/service.py",
            "from .contracts import ServiceBase\n\n\nclass Service(ServiceBase):\n    pass\n",
        ),
    ]);

    assert_eq!(
        class(&classes, "ServiceBase")["direct_subclasses"],
        json!(["Service"])
    );
    assert_eq!(class(&classes, "ServiceBase")["descendant_count"], 1);
}

#[test]
fn a_base_somebody_builds_or_exports_is_not_kept_only_for_its_subclass() {
    let classes = enriched(&[
        ("shop/__init__.py", "from .support import ServiceSupport\n"),
        (
            "shop/support.py",
            "class ServiceSupport:\n    def normalize(self, value):\n        return value\n",
        ),
        (
            "shop/service.py",
            "from .support import ServiceSupport\n\n\nclass Service(ServiceSupport):\n    pass\n\n\nheld = ServiceSupport()\n",
        ),
    ]);
    let base = class(&classes, "ServiceSupport");

    assert_eq!(base["is_instantiated"], true);
    assert_eq!(base["is_exported"], true);
    assert_eq!(base["only_cross_module_reference_is_subclass"], false);
}

#[test]
fn a_base_exported_by_its_own_module_is_not_proposed_for_removal() {
    let classes = enriched(&[
        ("shop/__init__.py", ""),
        (
            "shop/support.py",
            "__all__ = ['ServiceSupport']\n\n\nclass ServiceSupport:\n    pass\n",
        ),
        (
            "shop/service.py",
            "from .support import ServiceSupport\n\n\nclass Service(ServiceSupport):\n    pass\n",
        ),
    ]);

    assert_eq!(
        class(&classes, "Service")["base_is_removable_overlap"],
        false
    );
}

#[test]
fn two_bases_supplying_one_concrete_method_are_an_order_sensitive_hierarchy() {
    let classes = enriched(&[
        ("shop/__init__.py", ""),
        (
            "shop/loaders.py",
            "class JsonLoader:\n    def load(self):\n        return 1\n\n\nclass CachedLoader:\n    def load(self):\n        return 2\n\n\nclass Service(JsonLoader, CachedLoader):\n    pass\n\n\nclass Polite(JsonLoader, CachedLoader):\n    def load(self):\n        return super().load()\n",
        ),
    ]);

    assert_eq!(
        class(&classes, "Service")["has_noncooperative_concrete_collision"],
        true
    );
    assert_eq!(
        class(&classes, "Service")["has_redundant_direct_base"],
        false
    );
}

#[test]
fn a_base_that_already_inherits_another_base_is_a_redundant_direct_edge() {
    let classes = enriched(&[
        ("shop/__init__.py", ""),
        (
            "shop/layers.py",
            "class Contract:\n    def run(self):\n        return 1\n\n\nclass Middle(Contract):\n    def other(self):\n        return 2\n\n\nclass Leaf(Middle, Contract):\n    pass\n",
        ),
    ]);

    assert_eq!(class(&classes, "Leaf")["has_redundant_direct_base"], true);
}

#[test]
fn a_model_two_packages_import_proposes_the_file_below_the_package_they_share() {
    let classes = enriched(&[
        ("shop/__init__.py", ""),
        ("shop/orders/__init__.py", ""),
        ("shop/billing/__init__.py", ""),
        (
            "shop/types.py",
            "from pydantic import BaseModel\n\n\nclass OrderLine(BaseModel):\n    total: int\n",
        ),
        (
            "shop/orders/place.py",
            "from ..types import OrderLine\n\n\ndef place(line: OrderLine) -> int:\n    return line.total\n",
        ),
        (
            "shop/billing/charge.py",
            "from ..types import OrderLine\n\n\ndef charge(line: OrderLine) -> int:\n    return line.total\n",
        ),
    ]);
    let model = class(&classes, "OrderLine");

    assert_eq!(model["is_declarative_model"], true);
    assert_eq!(model["has_ordinary_behavior"], false);
    assert_eq!(
        model["importing_modules"],
        json!(["shop.billing.charge", "shop.orders.place"])
    );
    assert_eq!(
        model["proposed_model_destination"],
        "shop/models/order_line.py"
    );
}

#[test]
fn a_model_one_package_imports_proposes_that_package_own_models_module() {
    let classes = enriched(&[
        ("shop/__init__.py", ""),
        ("shop/orders/__init__.py", ""),
        (
            "shop/orders/types.py",
            "from pydantic import BaseModel\n\n\nclass OrderLine(BaseModel):\n    total: int\n",
        ),
        (
            "shop/orders/place.py",
            "from .types import OrderLine\n\n\ndef place(line: OrderLine) -> int:\n    return line.total\n",
        ),
        (
            "shop/orders/audit.py",
            "from .types import OrderLine\n\n\ndef audit(line: OrderLine) -> int:\n    return line.total\n",
        ),
    ]);

    assert_eq!(
        class(&classes, "OrderLine")["proposed_model_destination"],
        "shop/orders/models.py"
    );
}

#[test]
fn tests_do_not_claim_ownership_of_a_production_model() {
    let classes = enriched(&[
        ("shop/__init__.py", ""),
        (
            "shop/types.py",
            "from pydantic import BaseModel\n\n\nclass OrderLine(BaseModel):\n    total: int\n",
        ),
        ("tests/__init__.py", ""),
        (
            "tests/test_orders.py",
            "from shop.types import OrderLine\n\n\ndef test_order():\n    assert OrderLine(total=1)\n",
        ),
        (
            "tests/test_billing.py",
            "from shop.types import OrderLine\n\n\ndef test_charge():\n    assert OrderLine(total=1)\n",
        ),
    ]);
    let model = class(&classes, "OrderLine");

    assert_eq!(
        model["importing_modules"],
        json!(["tests.test_billing", "tests.test_orders"])
    );
    assert_eq!(model["proposed_model_destination"], "");
}

#[test]
fn dotted_root_filenames_do_not_invent_a_package_directory() {
    let classes = enriched(&[
        ("shop/__init__.py", ""),
        (
            "shop/types.py",
            "from pydantic import BaseModel\n\n\nclass OrderLine(BaseModel):\n    total: int\n",
        ),
        (
            "consumer.one.py",
            "from shop.types import OrderLine\n\n\ndef first(line: OrderLine) -> int:\n    return line.total\n",
        ),
        (
            "consumer.two.py",
            "from shop.types import OrderLine\n\n\ndef second(line: OrderLine) -> int:\n    return line.total\n",
        ),
    ]);

    assert_eq!(
        class(&classes, "OrderLine")["proposed_model_destination"],
        ""
    );
}

#[test]
fn a_model_foundation_and_a_property_service_are_not_records_to_move() {
    let classes = enriched(&[
        ("shop/__init__.py", ""),
        (
            "shop/bases.py",
            "from pydantic import BaseModel\n\n\nclass Model(BaseModel):\n    pass\n",
        ),
        (
            "shop/discovery.py",
            "from functools import cached_property\nfrom .bases import Model\n\n\nclass Discovery(Model):\n    package: str\n\n    @cached_property\n    def modules(self):\n        return []\n",
        ),
    ]);

    assert_eq!(class(&classes, "Model")["is_declarative_model"], false);
    assert_eq!(class(&classes, "Discovery")["is_declarative_model"], true);
    assert_eq!(class(&classes, "Discovery")["has_ordinary_behavior"], true);
}

#[test]
fn a_model_remains_declarative_below_a_project_owned_intermediate_base() {
    let classes = enriched(&[
        ("shop/__init__.py", ""),
        (
            "shop/bases.py",
            "from patos import FrozenModel\n\n\nclass Fact(FrozenModel):\n    pass\n",
        ),
        (
            "shop/facts.py",
            "from .bases import Fact\n\n\nclass OrderFact(Fact):\n    total: int\n",
        ),
    ]);

    assert_eq!(class(&classes, "OrderFact")["is_declarative_model"], true);
}

#[test]
fn a_subclass_carries_state_owned_by_any_resolved_ancestor() {
    let classes = enriched(&[
        ("shop/__init__.py", ""),
        (
            "shop/bases.py",
            "from patos import FrozenModel\n\n\nclass Record(FrozenModel):\n    value: int\n",
        ),
        (
            "shop/orders.py",
            "from .bases import Record\n\n\nclass Order(Record):\n    pass\n\n\nclass SpecialOrder(Order):\n    pass\n",
        ),
    ]);

    assert_eq!(class(&classes, "Order")["has_inherited_fields"], true);
    assert_eq!(
        class(&classes, "SpecialOrder")["has_inherited_fields"],
        true
    );
}

#[test]
fn two_short_role_types_two_modules_import_together_propose_one_namespace() {
    let sources = [
        ("shop/__init__.py", ""),
        (
            "shop/message.py",
            "class MessageContent:\n    pass\n\n\nclass MessageKind:\n    pass\n",
        ),
        (
            "shop/api.py",
            "from .message import MessageContent, MessageKind\n\n\ndef read(content: MessageContent, kind: MessageKind) -> None:\n    return None\n",
        ),
        (
            "shop/jobs.py",
            "from .message import MessageContent, MessageKind\n\n\ndef sweep(content: MessageContent, kind: MessageKind) -> None:\n    return None\n",
        ),
    ];
    let facts = extracted(&sources);
    let group = facts["ClassFact"]
        .iter()
        .flat_map(|fact| {
            fact["coupled_groups"]
                .as_array()
                .cloned()
                .unwrap_or_default()
        })
        .next()
        .expect("the group is proposed");

    assert_eq!(
        json!([
            group["prefix"],
            group["role_suffixes"],
            group["type_count"],
            group["coimporting_module_count"],
        ]),
        json!(["Message", ["Content", "Kind"], 2, 2])
    );
}

#[test]
fn a_class_this_repository_never_heard_of_leaves_the_record_alone() {
    let classes = enriched(&[("alone.py", "class Report:\n    pass\n")]);

    assert_eq!(class(&classes, "Report")["descendant_count"], 0);
    assert_eq!(
        class(&classes, "Report")["direct_subclasses"],
        json!([] as [&str; 0])
    );
}
