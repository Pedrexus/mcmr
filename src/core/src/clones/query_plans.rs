use crate::walk::{annotation_name, blocks, children, expressions, walk};
use ruff_python_ast::{Expr, ModModule, Stmt, StmtAssign};
use ruff_text_size::{Ranged, TextRange};
use std::collections::BTreeSet;

/// Return maximal expressions proven to describe table queries inside one function.
pub(super) fn polars_query_plans(module: &ModModule) -> Vec<TextRange> {
    let imported = module.body.iter().any(|statement| {
        matches!(statement, Stmt::Import(item) if item.names.iter().any(|alias| {
            alias.name.as_str() == "polars"
                && alias.asname.as_ref().is_some_and(|name| name.as_str() == "pl")
        }))
    });
    let mut collector = QueryPlanCollector {
        imported,
        plans: Vec::new(),
    };
    for statement in walk(module) {
        if let Stmt::FunctionDef(function) = statement {
            collector.collect_block(&function.body, &table_parameters(function));
        }
    }
    collector.plans.sort_unstable_by_key(|range| range.start());
    collector.plans.dedup();
    collector.plans
}

/// Return parameters whose annotation proves that their values are declarative table plans.
fn table_parameters(function: &ruff_python_ast::StmtFunctionDef) -> BTreeSet<String> {
    function
        .parameters
        .iter()
        .filter_map(|parameter| {
            let kind = annotation_name(parameter.annotation()?);
            matches!(kind.as_str(), "Table" | "LazyFrame" | "DataFrame")
                .then(|| parameter.name().to_string())
        })
        .collect()
}

/// Follow table query identities while keeping their import state and emitted plans together.
struct QueryPlanCollector {
    imported: bool,
    plans: Vec<TextRange>,
}

impl QueryPlanCollector {
    /// Forget one simple local binding that no longer names a table plan.
    fn forget_binding(target: &Expr, known: &mut BTreeSet<String>) {
        if let Expr::Name(name) = target {
            known.remove(name.id.as_str());
        }
    }

    /// Whether a call constructs one of the rule layer's table relation helpers.
    fn is_table_constructor(function: &Expr) -> bool {
        matches!(function, Expr::Name(name)
            if name.id.as_str().ends_with("Table") || name.id.as_str().ends_with("Tables"))
    }

    /// Retain one simple local binding as a proven table plan.
    fn remember_binding(target: &Expr, known: &mut BTreeSet<String>) {
        if let Expr::Name(name) = target {
            known.insert(name.id.to_string());
        }
    }

    /// Record one annotated assignment and retain whether its target names a table plan.
    fn collect_annotated_assignment(
        &mut self,
        value: Option<&Expr>,
        target: &Expr,
        known: &mut BTreeSet<String>,
    ) {
        let Some(value) = value else {
            Self::forget_binding(target, known);
            return;
        };
        self.collect_expressions(value, known);
        if self.is_query_plan(value, known) {
            Self::remember_binding(target, known);
        } else {
            Self::forget_binding(target, known);
        }
    }

    /// Record one ordinary assignment and retain whether its targets now name a table plan.
    fn collect_assignment(&mut self, assignment: &StmtAssign, known: &mut BTreeSet<String>) {
        let value = assignment.value.as_ref();
        let targets = assignment.targets.as_slice();
        let proven = self.is_query_plan(value, known);
        if proven && matches!(targets, [target] if matches!(target, Expr::Name(_))) {
            self.plans.push(assignment.range());
        } else {
            self.collect_expressions(value, known);
        }
        for target in targets {
            if proven {
                Self::remember_binding(target, known);
            } else {
                Self::forget_binding(target, known);
            }
        }
    }

    /// Follow proven plans through straight-line assignments without leaking branch state outward.
    fn collect_block(&mut self, body: &[Stmt], inherited: &BTreeSet<String>) {
        let mut known = inherited.clone();
        for statement in body {
            if matches!(statement, Stmt::FunctionDef(_) | Stmt::ClassDef(_)) {
                continue;
            }
            self.collect_statement(statement, &mut known);
            for block in blocks(statement) {
                self.collect_block(block, &known);
            }
        }
    }

    /// Keep the largest proven chain and leave every ordinary expression subtree visible.
    fn collect_expressions(&mut self, expression: &Expr, known: &BTreeSet<String>) {
        if self.is_query_plan(expression, known) {
            self.plans.push(expression.range());
            return;
        }
        for child in children(expression) {
            self.collect_expressions(child, known);
        }
    }

    fn collect_statement(&mut self, statement: &Stmt, known: &mut BTreeSet<String>) {
        match statement {
            Stmt::Assign(assignment) => self.collect_assignment(assignment, known),
            Stmt::AnnAssign(assignment) => self.collect_annotated_assignment(
                assignment.value.as_deref(),
                &assignment.target,
                known,
            ),
            Stmt::AugAssign(assignment) => {
                self.collect_expressions(&assignment.value, known);
                Self::forget_binding(&assignment.target, known);
            }
            _ => expressions(statement)
                .into_iter()
                .for_each(|expression| self.collect_expressions(expression, known)),
        }
    }

    /// Whether chaining starts from a table constructor, typed parameter, `pl`, or an alias.
    fn is_query_plan(&self, expression: &Expr, known: &BTreeSet<String>) -> bool {
        match expression {
            Expr::Name(name) => {
                known.contains(name.id.as_str()) || self.imported && name.id.as_str() == "pl"
            }
            Expr::Attribute(attribute) => self.is_query_plan(&attribute.value, known),
            Expr::Call(call) => {
                Self::is_table_constructor(&call.func) || self.is_query_plan(&call.func, known)
            }
            Expr::Subscript(subscript) => self.is_query_plan(&subscript.value, known),
            _ => false,
        }
    }
}
