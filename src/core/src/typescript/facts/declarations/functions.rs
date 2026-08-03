use super::shared::{
    declaration_visibility, declared_class, declared_function, member_name, member_visibility,
};
use crate::functions::FunctionRecord;
use crate::graph::Visibility;
use crate::source::Source;
use crate::typescript::callables::{
    body_lines, conditionals, control_increments, parameters, statement_count,
};
use crate::typescript::support::range;
use oxc_ast::ast::{ClassElement, Function, MethodDefinition, Program};
use oxc_span::GetSpan;

pub(in crate::typescript::facts) fn function_facts(
    source: &Source,
    program: &Program,
) -> Vec<FunctionRecord> {
    let mut facts = Vec::new();
    for statement in &program.body {
        if let Some(function) = declared_function(statement) {
            facts.push(
                FunctionFact::declaration(source, function, declaration_visibility(statement))
                    .build(),
            );
        }
        if let Some(class) = declared_class(statement) {
            facts.extend(method_facts(source, &class.body.body));
        }
    }
    facts
}

fn method_facts(source: &Source, members: &[ClassElement<'_>]) -> Vec<FunctionRecord> {
    members
        .iter()
        .filter_map(|member| match member {
            ClassElement::MethodDefinition(method) => {
                let name = member_name(method)?;
                Some(FunctionFact::method(source, method, name).build())
            }
            _ => None,
        })
        .collect()
}

struct FunctionFact<'a, 'ast> {
    source: &'a Source,
    function: &'a Function<'ast>,
    name: String,
    scope: String,
    visibility: Visibility,
}

impl<'a, 'ast> FunctionFact<'a, 'ast> {
    fn declaration(
        source: &'a Source,
        function: &'a Function<'ast>,
        visibility: Visibility,
    ) -> Self {
        let name = function
            .id
            .as_ref()
            .map(|item| item.name.to_string())
            .expect("a TypeScript function declaration must state its name");
        Self {
            source,
            function,
            name,
            scope: "module".to_string(),
            visibility,
        }
    }

    fn method(source: &'a Source, method: &'a MethodDefinition<'ast>, name: String) -> Self {
        Self {
            source,
            function: &method.value,
            name,
            scope: "method".to_string(),
            visibility: member_visibility(method),
        }
    }

    fn build(self) -> FunctionRecord {
        let mut record = self.identity();
        self.measurements(&mut record);
        record
    }

    fn identity(&self) -> FunctionRecord {
        let span = range(self.function.span());
        let mut record =
            FunctionRecord::new(self.source.span(span), "typescript", self.name.clone());
        record.identity.scope.clone_from(&self.scope);
        record.presentation.visibility = self.visibility.as_str().to_string();
        record.presentation.nodes.definition = Some(self.source.node("function", span));
        record
    }

    fn measurements(&self, record: &mut FunctionRecord) {
        let increments = control_increments(self.function.body.as_deref());
        record.semantics.roles.is_async = self.function.r#async;
        record.structure.implementation_lines = body_lines(self.source, self.function);
        record.structure.direct_statement_count = statement_count(self.function.body.as_deref());
        record.measures.conditional_count = conditionals(&increments);
        record.structure.control_increments = increments;
        record.structure.parameters = parameters(self.source, self.function);
    }
}
