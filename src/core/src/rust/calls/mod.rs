use crate::calls::{CallRecord, CallSite};
use crate::source::Source;
use proc_macro2::Span;
use std::collections::BTreeSet;
use syn::spanned::Spanned;
use syn::visit::Visit;

use super::support::{declared_name, path_name, source_span};
use super::syntax::expression_name;

/// Every call this module states, with the ones whose result nobody takes marked as such.
pub(super) fn call_fact(source: &Source, file: &syn::File) -> CallRecord {
    let mut found = Calls {
        source,
        calls: Vec::new(),
        discarded: BTreeSet::new(),
    };
    found.visit_file(file);
    let mut record = CallRecord::new(
        format!("calls:{}", source.relative),
        source_span(source, Span::call_site()),
        "rust",
    );
    record.calls = found.calls;
    record.module_bindings = file.items.iter().filter_map(declared_name).collect();
    record
}

/// Every call one module makes, collected as the visitor meets them.
///
/// A call in statement position ending in a semicolon is the one shape where the language throws
/// the result away, so that is what marks a discarded result. Everything else hands its value to
/// something, even when that something ignores it later, which is a question about the receiver.
struct Calls<'a> {
    source: &'a Source,
    calls: Vec<CallSite>,
    discarded: BTreeSet<(usize, usize)>,
}

impl Calls<'_> {
    fn record(&mut self, named: String, at: Span) {
        let opened = at.start();
        let closed = at.end();
        let range = self.source.range_location(opened..closed);
        let mut call = CallSite::new(named, self.source.node("call", range));
        call.result_is_discarded = self.discarded.contains(&(opened.line, opened.column));
        self.calls.push(call);
    }
}

impl Visit<'_> for Calls<'_> {
    fn visit_expr_call(&mut self, held: &syn::ExprCall) {
        self.record(expression_name(&held.func), held.span());
        syn::visit::visit_expr_call(self, held);
    }

    fn visit_expr_method_call(&mut self, held: &syn::ExprMethodCall) {
        self.record(held.method.to_string(), held.span());
        syn::visit::visit_expr_method_call(self, held);
    }

    fn visit_expr_struct(&mut self, held: &syn::ExprStruct) {
        self.record(path_name(&held.path), held.span());
        syn::visit::visit_expr_struct(self, held);
    }

    fn visit_stmt(&mut self, statement: &syn::Stmt) {
        if let syn::Stmt::Expr(held, Some(_)) = statement
            && matches!(
                held,
                syn::Expr::Call(_) | syn::Expr::MethodCall(_) | syn::Expr::Struct(_)
            )
        {
            let opened = held.span().start();
            self.discarded.insert((opened.line, opened.column));
        }
        syn::visit::visit_stmt(self, statement);
    }
}
