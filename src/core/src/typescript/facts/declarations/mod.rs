pub(in crate::typescript::facts) use classes::class_fact;
pub(in crate::typescript::facts) use functions::function_facts;
pub(in crate::typescript::facts) use shared::{
    declared_class, declared_function, declared_name, member_name,
};

mod classes;
mod functions;
mod shared;
