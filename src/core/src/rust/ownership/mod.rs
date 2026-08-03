use crate::protocol::JsonObject;
use crate::source::Source;
use proc_macro2::Span;
use serde_json::{Value, json};
use syn::visit::Visit;
use syn::{FnArg, Signature};

use super::support::{base, rendered_expression};

mod beyond;
mod impl_trait_lifetimes;
mod placed;
mod surface;

use beyond::Beyond;
use impl_trait_lifetimes::ImplTraitLifetimes;
use placed::Placed;
use surface::Surface;

/// What one module borrows, what it pins for the whole program, and what it copies instead.
///
/// These three belong in one fact because they are one decision seen from three sides. A lifetime
/// is what borrowing costs in the signature, a clone is what not borrowing costs at run time, and
/// a `'static` is what pinning costs forever. A rule that saw only one of them would push a
/// project straight into the other.
pub(super) fn surface_fact(source: &Source, file: &syn::File) -> Value {
    let mut surface = Surface::default();
    surface.visit_file(file);
    JsonObject::new(base(
        source,
        &format!("surface:{}", source.relative),
        Span::call_site(),
    ))
    .merged(json!({
        "annotations": surface.annotations,
        "pins": surface.pins,
        "clones": surface.clones,
    }))
}

impl Surface {
    fn owner(&self) -> String {
        self.owners.last().cloned().unwrap_or_default()
    }

    /// Record the lifetimes one declaration names and every position each of them appears in.
    ///
    /// Where a lifetime appears is what decides whether elision would have produced it, and where
    /// is something only a parser can see. What that arrangement means is a judgment, so it is
    /// left to the rule and only the arrangement is stated here.
    fn annotate(&mut self, generics: &syn::Generics, kind: &str, at: &syn::Ident, at_use: Placed) {
        let names: Vec<String> = generics
            .lifetimes()
            .map(|held| held.lifetime.ident.to_string())
            .collect();
        if names.is_empty() {
            return;
        }
        self.annotations.push(json!({
            "owner": format!("{}{}", self.owner(), at),
            "kind": kind,
            "names": names,
            "line": at.span().start().line,
            "returned": at_use.returned,
            "receiver": at_use.receiver,
            "parameters": at_use.parameters,
            "beyond": at_use.beyond,
            "required_by_syntax": at_use.required_by_syntax,
        }));
    }
}

/// Read where one signature names each of its lifetimes.
///
/// The four places are the ones the elision rules distinguish: what the return states, what the
/// receiver carries, what the other parameters name, and what the bounds, the where clause, or the
/// body still need. A rule reading these four decides whether the annotation says anything the
/// compiler would not have said on its own.
fn placed(signature: &Signature, body: &syn::Block) -> Placed {
    let mut returns = Beyond::default();
    returns.visit_return_type(&signature.output);
    let beyond = beyond_signature(signature, body);
    let (parameters, required_by_syntax) = parameter_lifetimes(signature);
    Placed {
        returned: returns.names,
        receiver: signature
            .receiver()
            .and_then(syn::Receiver::lifetime)
            .map(|held| held.ident.to_string())
            .unwrap_or_default(),
        parameters,
        beyond,
        required_by_syntax,
    }
}

fn beyond_signature(signature: &Signature, body: &syn::Block) -> Vec<String> {
    let mut beyond = Beyond::default();
    for parameter in &signature.generics.params {
        if let syn::GenericParam::Type(held) = parameter {
            for bound in &held.bounds {
                beyond.visit_type_param_bound(bound);
            }
        }
    }
    if let Some(clause) = &signature.generics.where_clause {
        beyond.visit_where_clause(clause);
    }
    beyond.visit_block(body);
    beyond.names
}

fn parameter_lifetimes(signature: &Signature) -> (Vec<String>, Vec<String>) {
    let mut parameters = Beyond::default();
    let mut required_by_syntax = ImplTraitLifetimes::default();
    for argument in &signature.inputs {
        if let FnArg::Typed(held) = argument {
            parameters.visit_type(&held.ty);
            required_by_syntax.visit_type(&held.ty);
        }
    }
    (parameters.names, required_by_syntax.names)
}

impl Visit<'_> for ImplTraitLifetimes {
    fn visit_type_impl_trait(&mut self, held: &syn::TypeImplTrait) {
        let mut names = Beyond::default();
        syn::visit::visit_type_impl_trait(&mut names, held);
        self.names.extend(names.names);
    }
}

impl Visit<'_> for Beyond {
    fn visit_lifetime(&mut self, held: &syn::Lifetime) {
        self.names.push(held.ident.to_string());
    }
}

/// Walk one module for the three things it says about ownership.
impl Visit<'_> for Surface {
    fn visit_item_fn(&mut self, declared: &syn::ItemFn) {
        self.annotate(
            &declared.sig.generics,
            "function",
            &declared.sig.ident,
            placed(&declared.sig, &declared.block),
        );
        self.owners.push(format!("{}::", declared.sig.ident));
        syn::visit::visit_item_fn(self, declared);
        self.owners.pop();
    }

    fn visit_impl_item_fn(&mut self, declared: &syn::ImplItemFn) {
        self.annotate(
            &declared.sig.generics,
            "method",
            &declared.sig.ident,
            placed(&declared.sig, &declared.block),
        );
        self.owners.push(format!("{}::", declared.sig.ident));
        syn::visit::visit_impl_item_fn(self, declared);
        self.owners.pop();
    }

    fn visit_item_struct(&mut self, declared: &syn::ItemStruct) {
        self.annotate(
            &declared.generics,
            "type",
            &declared.ident,
            Placed::default(),
        );
        syn::visit::visit_item_struct(self, declared);
    }

    fn visit_item_enum(&mut self, declared: &syn::ItemEnum) {
        self.annotate(
            &declared.generics,
            "type",
            &declared.ident,
            Placed::default(),
        );
        syn::visit::visit_item_enum(self, declared);
    }

    fn visit_item_trait(&mut self, declared: &syn::ItemTrait) {
        self.annotate(
            &declared.generics,
            "trait",
            &declared.ident,
            Placed::default(),
        );
        syn::visit::visit_item_trait(self, declared);
    }

    fn visit_item_type(&mut self, declared: &syn::ItemType) {
        self.annotate(
            &declared.generics,
            "alias",
            &declared.ident,
            Placed::default(),
        );
        syn::visit::visit_item_type(self, declared);
    }

    fn visit_type_param_bound(&mut self, bound: &syn::TypeParamBound) {
        if let syn::TypeParamBound::Lifetime(held) = bound
            && held.ident == "static"
        {
            self.pins.push(json!({
                "owner": self.owner(),
                "line": held.ident.span().start().line,
                "position": "bound",
            }));
            return;
        }
        syn::visit::visit_type_param_bound(self, bound);
    }

    fn visit_lifetime(&mut self, held: &syn::Lifetime) {
        if held.ident == "static" {
            self.pins.push(json!({
                "owner": self.owner(),
                "line": held.ident.span().start().line,
                "position": if self.demanding { "demand" } else { "supply" },
            }));
        }
    }

    /// Walk a signature knowing which side of it each type sits on.
    ///
    /// A pin in a parameter is a demand on the caller and a pin in a return is a promise to it,
    /// and only one of those forecloses anything, so the two cannot be counted the same way.
    fn visit_signature(&mut self, signature: &Signature) {
        for argument in &signature.inputs {
            self.demanding = true;
            syn::visit::visit_fn_arg(self, argument);
            self.demanding = false;
        }
        syn::visit::visit_return_type(self, &signature.output);
        syn::visit::visit_generics(self, &signature.generics);
    }

    fn visit_field(&mut self, field: &syn::Field) {
        self.demanding = true;
        syn::visit::visit_field(self, field);
        self.demanding = false;
    }

    fn visit_expr_method_call(&mut self, call: &syn::ExprMethodCall) {
        if matches!(call.method.to_string().as_str(), "clone" | "to_owned") {
            self.clones.push(json!({
                "receiver": rendered_expression(&call.receiver),
                "owner": self.owner(),
                "line": call.method.span().start().line,
                "loop_depth": self.loop_depth,
            }));
        }
        syn::visit::visit_expr_method_call(self, call);
    }

    fn visit_expr_for_loop(&mut self, held: &syn::ExprForLoop) {
        self.loop_depth += 1;
        syn::visit::visit_expr_for_loop(self, held);
        self.loop_depth -= 1;
    }

    fn visit_expr_while(&mut self, held: &syn::ExprWhile) {
        self.loop_depth += 1;
        syn::visit::visit_expr_while(self, held);
        self.loop_depth -= 1;
    }

    fn visit_expr_loop(&mut self, held: &syn::ExprLoop) {
        self.loop_depth += 1;
        syn::visit::visit_expr_loop(self, held);
        self.loop_depth -= 1;
    }
}
