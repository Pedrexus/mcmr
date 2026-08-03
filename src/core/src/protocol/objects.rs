use serde_json::Value;

/// One JSON object ready to consume another object's fields.
pub(crate) struct JsonObject(Value);

impl JsonObject {
    pub(crate) fn new(value: Value) -> Self {
        Self(value)
    }

    pub(crate) fn merged(mut self, additions: Value) -> Value {
        let Value::Object(additions) = additions else {
            panic!("JSON object additions must be an object");
        };
        let Value::Object(target) = &mut self.0 else {
            panic!("a JSON object target must be an object");
        };
        target.extend(additions);
        self.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn additions_extend_an_object_and_win_duplicate_keys() {
        let merged = JsonObject::new(json!({"kept": 1, "replaced": 2}))
            .merged(json!({"replaced": 3, "added": 4}));

        assert_eq!(merged, json!({"kept": 1, "replaced": 3, "added": 4}));
    }

    #[test]
    #[should_panic(expected = "target must be an object")]
    fn a_non_object_target_fails_loudly() {
        let _ = JsonObject::new(json!([])).merged(json!({}));
    }

    #[test]
    #[should_panic(expected = "additions must be an object")]
    fn non_object_additions_fail_loudly() {
        let _ = JsonObject::new(json!({})).merged(json!([]));
    }
}
