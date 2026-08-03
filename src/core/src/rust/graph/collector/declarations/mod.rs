use super::Collector;
use crate::graph::{
    DatatypeKind, EdgeKind, Language, Node, NodeKind, ParameterKind, Relation, Visibility,
    identity, node, parameter,
};
use crate::rust::classes::{bound_names, derives, external_attributes, type_names};
use crate::rust::graph::callable::CallableDefinition;
use crate::rust::graph::callable_identity::CallableIdentity;
use crate::rust::support::{path_name, rendered, spanned, visibility};
use syn::spanned::Spanned;
use syn::{FnArg, ImplItem, Item, ReturnType, Signature, TraitItem};

impl Collector {
    pub(in crate::rust::graph) fn items(&mut self, items: &[Item]) {
        for item in items {
            self.item(item);
        }
    }

    /// State what one item declares, what it names, and what its body reaches.
    ///
    /// Every arm follows the same shape: declare the node, relate it to whatever holds it, record
    /// the types it names, then walk into whatever body it carries. The kinds differ only in which
    /// of those four an item actually has.
    pub(super) fn item(&mut self, item: &Item) {
        match item {
            Item::Use(declared) => self.import(declared),
            Item::Mod(declared) => self.nested(declared),
            Item::Struct(declared) => {
                let identifier = self.datatype(
                    &declared.ident,
                    &declared.vis,
                    &declared.attrs,
                    DatatypeKind::Concrete,
                );
                for field in &declared.fields {
                    self.field(&identifier, field);
                }
            }
            Item::Union(declared) => {
                let identifier = self.datatype(
                    &declared.ident,
                    &declared.vis,
                    &declared.attrs,
                    DatatypeKind::Concrete,
                );
                for field in &declared.fields.named {
                    self.field(&identifier, field);
                }
            }
            Item::Enum(declared) => self.enumeration(declared),
            Item::Trait(declared) => self.contract(declared),
            Item::Type(declared) => {
                let identifier = self.datatype(
                    &declared.ident,
                    &declared.vis,
                    &declared.attrs,
                    DatatypeKind::Concrete,
                );
                self.types(&identifier, &declared.ty, declared.ident.span());
            }
            Item::Fn(declared) => {
                let qualname = format!("{}::{}", self.scope(), declared.sig.ident);
                let owner = self.owner();
                let identifier = self.callable(
                    CallableIdentity {
                        owner: &owner,
                        qualname: &qualname,
                    },
                    &declared.sig,
                    CallableDefinition {
                        attributes: &declared.attrs,
                        reach: visibility(&declared.vis),
                        span: declared.span(),
                    },
                );
                self.body(
                    CallableIdentity {
                        owner: &identifier,
                        qualname: &qualname,
                    },
                    &declared.block,
                );
            }
            Item::Impl(block) => self.implementation(block),
            Item::Const(declared) => {
                let identifier = self.constant(&declared.ident, &declared.vis);
                self.types(&identifier, &declared.ty, declared.ident.span());
                self.initializer(&identifier, &declared.expr);
            }
            Item::Static(declared) => {
                let identifier = self.constant(&declared.ident, &declared.vis);
                self.types(&identifier, &declared.ty, declared.ident.span());
                self.initializer(&identifier, &declared.expr);
            }
            _ => {}
        }
    }

    /// Walk into a module written inside this file, which its own name then qualifies.
    fn nested(&mut self, declared: &syn::ItemMod) {
        let qualname = format!("{}::{}", self.scope(), declared.ident);
        let mut held = node(Language::Rust, NodeKind::Module, &qualname);
        held.path = Some(self.source.relative.clone());
        held.line = Some(declared.ident.span().start().line);
        held.visibility = visibility(&declared.vis);
        self.declare(held, declared.ident.span());
        let Some((_, items)) = &declared.content else {
            return;
        };
        self.nested_items(qualname, items);
    }

    fn nested_items(&mut self, qualname: String, items: &[Item]) {
        let identifier = identity(Language::Rust, NodeKind::Module, &qualname);
        self.enclosing.push(qualname.clone());
        self.scopes.push(qualname);
        self.owners.push(identifier);
        self.items(items);
        self.owners.pop();
        self.scopes.pop();
        self.enclosing.pop();
    }

    /// Declare one enum, whose variants are the names the rest of the repository reads it by.
    fn enumeration(&mut self, declared: &syn::ItemEnum) {
        let qualname = format!("{}::{}", self.scope(), declared.ident);
        let identifier = self.datatype(
            &declared.ident,
            &declared.vis,
            &declared.attrs,
            DatatypeKind::Enumeration,
        );
        for variant in &declared.variants {
            let mut member = node(
                Language::Rust,
                NodeKind::Attribute,
                &format!("{qualname}::{}", variant.ident),
            );
            member.path = Some(self.source.relative.clone());
            member.line = Some(variant.ident.span().start().line);
            let member_id = member.id.clone();
            self.nodes.push(member);
            self.relate(
                Relation {
                    source: &identifier,
                    target: &member_id,
                    kind: EdgeKind::Define,
                },
                variant.ident.span(),
            );
            for field in &variant.fields {
                self.types(&identifier, &field.ty, variant.ident.span());
            }
        }
    }

    /// Declare one trait, the contract it extends, and every method it states.
    fn contract(&mut self, declared: &syn::ItemTrait) {
        let qualname = format!("{}::{}", self.scope(), declared.ident);
        let identifier = self.datatype(
            &declared.ident,
            &declared.vis,
            &declared.attrs,
            DatatypeKind::Contract,
        );
        for supertrait in &declared.supertraits {
            for name in bound_names(supertrait) {
                self.reference(
                    Relation {
                        source: &identifier,
                        target: &name,
                        kind: EdgeKind::Inherit,
                    },
                    declared.ident.span(),
                );
            }
        }
        for member in &declared.items {
            let TraitItem::Fn(method) = member else {
                continue;
            };
            let owned = format!("{qualname}::{}", method.sig.ident);
            let method_id = self.callable(
                CallableIdentity {
                    owner: &identifier,
                    qualname: &owned,
                },
                &method.sig,
                CallableDefinition {
                    attributes: &method.attrs,
                    reach: Visibility::Public,
                    span: member.span(),
                },
            );
            if let Some(body) = &method.default {
                self.body(
                    CallableIdentity {
                        owner: &method_id,
                        qualname: &owned,
                    },
                    body,
                );
            }
        }
    }

    /// Declare one named type, which is what a struct, an enum, a union, a trait, and an alias are.
    ///
    /// A derive is an implementation the compiler writes, so the type satisfies that trait exactly
    /// as it would with an impl block spelled out, and the graph says so.
    ///
    /// What the type promises travels with it, because a trait states a contract and provides none
    /// of it while every other item here is the implementation somebody has to write.
    fn datatype(
        &mut self,
        name: &syn::Ident,
        reach: &syn::Visibility,
        attributes: &[syn::Attribute],
        kind: DatatypeKind,
    ) -> String {
        let identifier = self.declare_datatype(name, reach, attributes, kind);
        for derived in derives(attributes) {
            self.reference(
                Relation {
                    source: &identifier,
                    target: &derived,
                    kind: EdgeKind::Inherit,
                },
                name.span(),
            );
        }
        identifier
    }

    fn declare_datatype(
        &mut self,
        name: &syn::Ident,
        reach: &syn::Visibility,
        attributes: &[syn::Attribute],
        kind: DatatypeKind,
    ) -> String {
        let qualname = format!("{}::{name}", self.scope());
        let mut declared = node(Language::Rust, NodeKind::Class, &qualname).datatype(kind);
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(name.span().start().line);
        declared.visibility = visibility(reach);
        declared.decorators = external_attributes(attributes);
        let identifier = declared.id.clone();
        self.declare(declared, name.span());
        identifier
    }

    fn constant(&mut self, name: &syn::Ident, reach: &syn::Visibility) -> String {
        let qualname = format!("{}::{name}", self.scope());
        let mut declared = node(Language::Rust, NodeKind::Variable, &qualname);
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(name.span().start().line);
        declared.visibility = visibility(reach);
        let identifier = declared.id.clone();
        self.declare(declared, name.span());
        identifier
    }

    fn field(&mut self, owner: &str, field: &syn::Field) {
        let span = field
            .ident
            .as_ref()
            .map_or_else(|| field.ty.span(), |name| name.span());
        if let Some(name) = &field.ident {
            let holder = owner.rsplit(':').next().unwrap_or_default();
            let mut declared = node(
                Language::Rust,
                NodeKind::Attribute,
                &format!("{holder}::{name}"),
            );
            declared.path = Some(self.source.relative.clone());
            declared.line = Some(span.start().line);
            declared.visibility = visibility(&field.vis);
            declared.annotation = Some(rendered(&field.ty));
            let identifier = declared.id.clone();
            self.nodes.push(declared);
            self.relate(
                Relation {
                    source: owner,
                    target: &identifier,
                    kind: EdgeKind::Define,
                },
                span,
            );
        }
        self.types(owner, &field.ty, span);
    }

    /// Declare one callable, the parameters it takes, and every type its signature names.
    fn callable(
        &mut self,
        identity: CallableIdentity<'_>,
        signature: &Signature,
        definition: CallableDefinition<'_>,
    ) -> String {
        let declared = self.callable_node(identity, signature, &definition);
        let identifier = declared.id.clone();
        self.nodes.push(declared);
        self.relate(
            Relation {
                source: identity.owner,
                target: &identifier,
                kind: EdgeKind::Define,
            },
            signature.ident.span(),
        );
        self.declare_parameters(identity.qualname, signature, &identifier);
        if let ReturnType::Type(_, returns) = &signature.output {
            self.types(&identifier, returns, signature.ident.span());
        }
        identifier
    }

    fn callable_node(
        &self,
        identity: CallableIdentity<'_>,
        signature: &Signature,
        definition: &CallableDefinition<'_>,
    ) -> Node {
        let kind = if identity.owner.contains(":class:") {
            NodeKind::Method
        } else {
            NodeKind::Function
        };
        let mut declared = node(Language::Rust, kind, identity.qualname);
        declared.path = Some(self.source.relative.clone());
        declared.line = Some(signature.ident.span().start().line);
        declared.source =
            (kind == NodeKind::Method).then(|| spanned(&self.source, definition.span).to_string());
        declared.visibility = definition.reach;
        declared.decorators = external_attributes(definition.attributes);
        declared.asynchronous = signature.asyncness.is_some();
        if let ReturnType::Type(_, returns) = &signature.output {
            declared.return_annotation = Some(rendered(returns));
        }
        declared
    }

    fn declare_parameters(&mut self, qualname: &str, signature: &Signature, identifier: &str) {
        // Rust binds every argument by position and has no defaults. State both parameter facts
        // from the language rather than leaving them unknown.
        for (ordinal, argument) in signature.inputs.iter().enumerate() {
            let FnArg::Typed(typed) = argument else {
                continue;
            };
            let syn::Pat::Ident(name) = typed.pat.as_ref() else {
                continue;
            };
            let mut held = parameter(
                Language::Rust,
                &format!("{}::{}", qualname, name.ident),
                ordinal,
                ParameterKind::PositionalOnly,
            );
            held.path = Some(self.source.relative.clone());
            held.line = Some(name.ident.span().start().line);
            held.annotation = Some(rendered(&typed.ty));
            let held_id = held.id.clone();
            self.nodes.push(held);
            self.relate(
                Relation {
                    source: identifier,
                    target: &held_id,
                    kind: EdgeKind::Define,
                },
                name.ident.span(),
            );
            self.types(identifier, &typed.ty, name.ident.span());
        }
    }

    /// State what one impl block adds to the type it names, and to the trait it satisfies.
    fn implementation(&mut self, block: &syn::ItemImpl) {
        let named = type_names(&block.self_ty);
        let Some(subject) = named.first() else {
            return;
        };
        let qualname = self.qualify(subject);
        let owner = identity(Language::Rust, NodeKind::Class, &qualname);
        if let Some((_, path, _)) = &block.trait_ {
            self.reference(
                Relation {
                    source: &owner,
                    target: &path_name(path),
                    kind: EdgeKind::Inherit,
                },
                block.impl_token.span,
            );
        }
        self.receiver = Some(qualname.clone());
        for member in &block.items {
            let ImplItem::Fn(method) = member else {
                continue;
            };
            let held = format!("{qualname}::{}", method.sig.ident);
            // A trait method is as reachable as the trait itself, whatever the impl block writes,
            // since a caller reaches it through the trait rather than through the type.
            let reach = match block.trait_ {
                Some(_) => Visibility::Public,
                None => visibility(&method.vis),
            };
            let identifier = self.callable(
                CallableIdentity {
                    owner: &owner,
                    qualname: &held,
                },
                &method.sig,
                CallableDefinition {
                    attributes: &method.attrs,
                    reach,
                    span: method.span(),
                },
            );
            self.body(
                CallableIdentity {
                    owner: &identifier,
                    qualname: &held,
                },
                &method.block,
            );
        }
        self.receiver = None;
    }
}
