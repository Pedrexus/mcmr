use crate::functions::{ControlIncrement, FunctionParameter, FunctionRecord};
use crate::graph::Visibility;
use crate::source::Source;
use syn::spanned::Spanned;
use syn::visit::Visit;
use syn::{FnArg, ImplItem, Item, Signature, TraitItem};

use super::support::{label, member_reach, spanned, visibility};

mod definition;

use definition::FunctionDefinition;

pub fn function_facts(source: &Source, file: &syn::File) -> Vec<FunctionRecord> {
    let mut facts = Vec::new();
    for item in &file.items {
        match item {
            Item::Fn(declared) => facts.push(function_fact(
                source,
                &declared.sig,
                FunctionDefinition {
                    declaration: declared.span(),
                    reach: visibility(&declared.vis),
                    scope: "module",
                    body: Some(&declared.block),
                },
            )),
            Item::Impl(block) => facts.extend(block.items.iter().filter_map(|member| {
                let ImplItem::Fn(method) = member else {
                    return None;
                };
                Some(function_fact(
                    source,
                    &method.sig,
                    FunctionDefinition {
                        declaration: method.span(),
                        reach: member_reach(block, &method.vis),
                        scope: "method",
                        body: Some(&method.block),
                    },
                ))
            })),
            Item::Trait(declared) => facts.extend(declared.items.iter().filter_map(|member| {
                let TraitItem::Fn(method) = member else {
                    return None;
                };
                Some(function_fact(
                    source,
                    &method.sig,
                    FunctionDefinition {
                        declaration: method.span(),
                        reach: Visibility::Public,
                        scope: "method",
                        body: method.default.as_ref(),
                    },
                ))
            })),
            _ => {}
        }
    }
    facts
}

fn function_fact(
    source: &Source,
    signature: &Signature,
    definition: FunctionDefinition<'_>,
) -> FunctionRecord {
    let increments = definition.body.map(control_increments).unwrap_or_default();
    let mut fact = identified_function(source, signature, &definition);
    describe_signature(&mut fact, source, signature);
    describe_body(&mut fact, &definition, increments);
    fact
}

fn identified_function(
    source: &Source,
    signature: &Signature,
    definition: &FunctionDefinition<'_>,
) -> FunctionRecord {
    let opened = definition.declaration.start();
    let closed = definition.declaration.end();
    let identified = signature.ident.span();
    let mut fact = FunctionRecord::new(
        source.span(source.range_location(identified.start()..identified.end())),
        "rust",
        signature.ident.to_string(),
    );
    fact.identity.scope = definition.scope.to_string();
    fact.presentation.visibility = label(definition.reach).to_string();
    fact.presentation.nodes.definition =
        Some(source.node("function", source.range_location(opened..closed)));
    fact
}

fn describe_signature(fact: &mut FunctionRecord, source: &Source, signature: &Signature) {
    fact.semantics.roles.is_async = signature.asyncness.is_some();
    fact.structure.parameters = signature
        .inputs
        .iter()
        .map(|parameter| parameter_fact(source, parameter))
        .collect();
}

fn describe_body(
    fact: &mut FunctionRecord,
    definition: &FunctionDefinition<'_>,
    increments: Vec<ControlIncrement>,
) {
    fact.structure.implementation_lines = definition.body.map_or(0, body_lines);
    fact.structure.direct_statement_count = definition.body.map_or(0, |held| held.stmts.len());
    fact.measures.conditional_count = increments
        .iter()
        .filter(|increment| increment.kind == "conditional")
        .count();
    fact.structure.control_increments = increments;
}

/// Return how many physical lines one body runs, from its first statement to its last.
///
/// The braces are left out because the signature is not the work, which is the same boundary the
/// reference frontend draws when it drops the declaration line and the docstring under it.
fn body_lines(body: &syn::Block) -> usize {
    let (Some(first), Some(last)) = (body.stmts.first(), body.stmts.last()) else {
        return 0;
    };
    last.span().end().line - first.span().start().line + 1
}

/// Return every control structure one body holds, each with the number enclosing it.
///
/// The kinds and the depth arithmetic are the reference frontend's, because the complexity and
/// nesting rules own one scoring model for every language and a second convention here would make
/// the same program measure differently depending on who wrote it. What genuinely differs is where
/// a language keeps its control flow. Python states it as statements, so its reader walks
/// statements; Rust states it as expressions, so a `match` bound to a name is the same structure as
/// a `match` standing on its own line and both have to be found.
fn control_increments(body: &syn::Block) -> Vec<ControlIncrement> {
    let mut found = Control::default();
    found.visit_block(body);
    found.increments
}

/// Every control structure one body states, collected as the walk meets them.
#[derive(Default)]
struct Control {
    depth: usize,
    increments: Vec<ControlIncrement>,
}

impl Control {
    /// Record one arm of a decision, which continues it rather than nesting inside it.
    ///
    /// `} else if {` is what this language spells `elif` with, so every arm of one chain sits at
    /// the depth the first `if` opened at. Reading the chain as a branch inside a branch would
    /// charge a reader a level of nesting the page never shows them.
    fn alternative(&mut self, otherwise: &syn::Expr) {
        self.record("alternative");
        match otherwise {
            syn::Expr::If(chained) => {
                syn::visit::visit_expr(self, &chained.cond);
                self.inside(&chained.then_branch);
                if let Some((_, next)) = &chained.else_branch {
                    self.alternative(next);
                }
            }
            syn::Expr::Block(held) => self.inside(&held.block),
            held => syn::visit::visit_expr(self, held),
        }
    }

    /// Walk one body knowing it sits one level deeper than the structure that opened it.
    fn inside(&mut self, held: &syn::Block) {
        self.depth += 1;
        syn::visit::visit_block(self, held);
        self.depth -= 1;
    }

    fn record(&mut self, kind: &str) {
        self.increments
            .push(ControlIncrement::new(kind, self.depth));
    }
}

impl Visit<'_> for Control {
    /// A closure is a callable of its own and states its own fact, exactly as a nested `def` does.
    fn visit_expr_closure(&mut self, _: &syn::ExprClosure) {}

    fn visit_expr_for_loop(&mut self, held: &syn::ExprForLoop) {
        self.record("loop");
        syn::visit::visit_expr(self, &held.expr);
        self.inside(&held.body);
    }

    fn visit_expr_if(&mut self, held: &syn::ExprIf) {
        self.record("conditional");
        syn::visit::visit_expr(self, &held.cond);
        self.inside(&held.then_branch);
        if let Some((_, otherwise)) = &held.else_branch {
            self.alternative(otherwise);
        }
    }

    fn visit_expr_loop(&mut self, held: &syn::ExprLoop) {
        self.record("loop");
        self.inside(&held.body);
    }

    fn visit_expr_match(&mut self, held: &syn::ExprMatch) {
        self.record("switch");
        syn::visit::visit_expr(self, &held.expr);
        self.depth += 1;
        for arm in &held.arms {
            syn::visit::visit_expr(self, &arm.body);
        }
        self.depth -= 1;
    }

    fn visit_expr_while(&mut self, held: &syn::ExprWhile) {
        self.record("loop");
        syn::visit::visit_expr(self, &held.cond);
        self.inside(&held.body);
    }

    /// A declaration written inside a body is a declaration, and the family reports it separately.
    fn visit_item(&mut self, _: &Item) {}
}

fn parameter_fact(source: &Source, argument: &FnArg) -> FunctionParameter {
    match argument {
        FnArg::Receiver(_) => {
            let mut fact = FunctionParameter::named("self".to_string());
            fact.contract.is_receiver = true;
            fact
        }
        FnArg::Typed(typed) => {
            let name = match typed.pat.as_ref() {
                syn::Pat::Ident(ident) => ident.ident.to_string(),
                pattern => spanned(source, pattern.span()).to_string(),
            };
            let type_name = spanned(source, typed.ty.span())
                .split_whitespace()
                .collect::<String>();
            let mut fact = FunctionParameter::named(name);
            fact.contract.has_boolean_annotation = type_name == "bool";
            fact.type_name = type_name;
            fact.contract.is_positional_only = true;
            fact.contract.is_required_by_external_contract = true;
            fact
        }
    }
}
