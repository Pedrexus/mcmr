use super::*;

#[test]
fn try_setup_accepts_only_simple_constants_before_the_next_raising_operation() {
    let text = concat!(
        "def load(stream):\n",
        "    try:\n",
        "        mode = 'rb'\n",
        "        limit = 4\n",
        "        payload = stream.read()\n",
        "    except OSError:\n",
        "        recover()\n",
        "    try:\n",
        "        values = []\n",
        "        consume(values)\n",
        "    except Error:\n",
        "        recover()\n",
        "    try:\n",
        "        first = second = 'ready'\n",
        "        consume(first)\n",
        "    except Error:\n",
        "        recover()\n",
        "    try:\n",
        "        holder.mode = 'ready'\n",
        "        consume(holder.mode)\n",
        "    except Error:\n",
        "        recover()\n",
        "    try:\n",
        "        items[0] = 'ready'\n",
        "        consume(items[0])\n",
        "    except Error:\n",
        "        recover()\n",
        "    try:\n",
        "        computed = make_value()\n",
        "        consume(computed)\n",
        "    except Error:\n",
        "        recover()\n",
        "    try:\n",
        "        note: str = 'ready'\n",
        "        consume(note)\n",
        "    except Error:\n",
        "        recover()\n",
        "    try:\n",
        "        typed = 'ready'  # type: str\n",
        "        consume(typed)\n",
        "    except Error:\n",
        "        recover()\n",
        "    try:\n",
        "        ready = True\n",
        "        return ready\n",
        "    except Error:\n",
        "        recover()\n",
    );
    let fact = fact(
        crate::discovery::Document {
            relative: "loader.py".to_string(),
            source: text.to_string(),
        },
        try_blocks,
    );
    let regions = fact["regions"].as_array().expect("try regions");

    assert_eq!(regions.len(), 9);
    assert_eq!(regions[0]["leading_literal_assignment_count"], 2);
    assert_eq!(regions[0]["has_following_raising_operation"], true);
    assert_eq!(regions[0]["leading_assignments"][0]["text"], "mode = 'rb'");
    assert!(
        regions[1..8]
            .iter()
            .all(|region| region["leading_literal_assignment_count"] == 0)
    );
    assert_eq!(regions[8]["leading_literal_assignment_count"], 1);
    assert_eq!(regions[8]["has_following_raising_operation"], false);
}

#[test]
fn try_setup_respects_callable_scopes_and_external_declarations() {
    let text = concat!(
        "try:\n",
        "    mode = 'rb'\n",
        "    read()\n",
        "except Error:\n",
        "    recover()\n\n",
        "class Reader:\n",
        "    try:\n",
        "        mode = 'rb'\n",
        "        read()\n",
        "    except Error:\n",
        "        recover()\n",
        "    def method(self):\n",
        "        try:\n",
        "            mode = 'rb'\n",
        "            read()\n",
        "        except Error:\n",
        "            recover()\n\n",
        "global_mode = ''\n",
        "def global_user():\n",
        "    global global_mode\n",
        "    try:\n",
        "        global_mode = 'rb'\n",
        "        read()\n",
        "    except Error:\n",
        "        recover()\n\n",
        "def outer():\n",
        "    shared = ''\n",
        "    class Local:\n",
        "        try:\n",
        "            mode = 'rb'\n",
        "            read()\n",
        "        except Error:\n",
        "            recover()\n",
        "    def nested():\n",
        "        nonlocal shared\n",
        "        try:\n",
        "            shared = 'rb'\n",
        "            read()\n",
        "        except Error:\n",
        "            recover()\n",
        "    try:\n",
        "        mode = 'rb'\n",
        "        read()\n",
        "    except Error:\n",
        "        recover()\n",
    );
    let fact = fact(
        crate::discovery::Document {
            relative: "scopes.py".to_string(),
            source: text.to_string(),
        },
        try_blocks,
    );
    let regions = fact["regions"].as_array().expect("try regions");
    let qualifying = regions
        .iter()
        .filter(|region| region["leading_literal_assignment_count"] == 1)
        .count();

    assert_eq!(regions.len(), 7);
    assert_eq!(qualifying, 2);
}

#[test]
fn try_setup_uses_the_closed_raising_operation_set() {
    let text = concat!(
        "def operations(value, ready):\n",
        "    try:\n        marker = 1\n        import package\n    except Error:\n        pass\n",
        "    try:\n        marker = 1\n        value.attr\n    except Error:\n        pass\n",
        "    try:\n        marker = 1\n        value[0]\n    except Error:\n        pass\n",
        "    try:\n        marker = 1\n        value + 1\n    except Error:\n        pass\n",
        "    try:\n        marker = 1\n        value == 1\n    except Error:\n        pass\n",
        "    try:\n        marker = 1\n        assert ready\n    except Error:\n        pass\n",
        "    try:\n        marker = 1\n        raise Error\n    except Error:\n        pass\n",
        "    try:\n        marker = 1\n        for item in value:\n            pass\n    except Error:\n        pass\n",
        "    try:\n        marker = 1\n        with value:\n            pass\n    except Error:\n        pass\n",
        "    try:\n        marker = 1\n        consume(value)\n    except Error:\n        pass\n",
        "    try:\n        marker = 1\n        result = [item for item in value]\n    except Error:\n        pass\n",
        "    try:\n        marker = 1\n        value += 1\n    except Error:\n        pass\n",
        "    try:\n        marker = 1\n        result = -value\n    except Error:\n        pass\n",
        "    try:\n        marker = 1\n        result = not ready\n    except Error:\n        pass\n",
        "    try:\n        marker = 1\n        return value\n    except Error:\n        pass\n",
        "\nasync def asynchronous(value):\n",
        "    try:\n        marker = 1\n        result = await value\n    except Error:\n        pass\n",
        "\ndef generator(value):\n",
        "    try:\n        marker = 1\n        yield from value\n    except Error:\n        pass\n",
    );
    let fact = fact(
        crate::discovery::Document {
            relative: "operations.py".to_string(),
            source: text.to_string(),
        },
        try_blocks,
    );
    let regions = fact["regions"].as_array().expect("try regions");
    let answers: Vec<bool> = regions
        .iter()
        .map(|region| {
            region["has_following_raising_operation"]
                .as_bool()
                .expect("raising answer")
        })
        .collect();

    assert_eq!(answers.len(), 17);
    assert!(answers[..13].iter().all(|answer| *answer));
    assert_eq!(answers[13..], [false, false, true, true]);
}

#[test]
fn exception_clause_counts_recurse_without_crossing_new_scopes() {
    let text = concat!(
        "def process(items, manager, value):\n",
        "    try:\n",
        "        first()\n",
        "        if ready:\n",
        "            second()\n",
        "        for item in items:\n",
        "            third(item)\n",
        "        with manager:\n",
        "            fourth()\n",
        "        match value:\n",
        "            case 1:\n",
        "                fifth()\n",
        "        def inner():\n",
        "            hidden()\n",
        "        class Inner:\n",
        "            hidden()\n",
        "        try:\n",
        "            nested_a()\n",
        "            if ready:\n",
        "                nested_b()\n",
        "        except NestedError:\n",
        "            nested_recover()\n",
        "    except Error:\n",
        "        log()\n",
        "        raise\n",
        "    else:\n",
        "        done()\n",
        "    finally:\n",
        "        cleanup()\n",
    );
    let fact = fact(
        crate::discovery::Document {
            relative: "regions.py".to_string(),
            source: text.to_string(),
        },
        try_blocks,
    );
    let regions = fact["regions"].as_array().expect("try regions");

    assert_eq!(regions.len(), 2);
    assert_eq!(regions[0]["clause_statement_counts"], json!([9, 2, 1, 1]));
    assert_eq!(regions[1]["clause_statement_counts"], json!([3, 1]));
    assert_eq!(regions[0]["leading_literal_assignment_count"], 0);
}

#[test]
fn try_star_and_finally_only_suppress_the_literal_setup_candidate() {
    let text = concat!(
        "def guarded():\n",
        "    try:\n",
        "        mode = 'rb'\n",
        "        read()\n",
        "    except* Error:\n",
        "        recover()\n",
        "    try:\n",
        "        mode = 'rb'\n",
        "        read()\n",
        "    except Error:\n",
        "        recover()\n",
        "    finally:\n",
        "        close()\n",
    );
    let fact = fact(
        crate::discovery::Document {
            relative: "guarded.py".to_string(),
            source: text.to_string(),
        },
        try_blocks,
    );
    let regions = fact["regions"].as_array().expect("try regions");

    assert_eq!(regions.len(), 2);
    assert!(regions.iter().all(|region| {
        region["leading_literal_assignment_count"] == 0
            && region["has_following_raising_operation"] == false
    }));
    assert_eq!(regions[0]["clause_statement_counts"], json!([2, 1]));
    assert_eq!(regions[1]["clause_statement_counts"], json!([2, 1, 1]));
}

#[test]
fn try_regions_retain_protected_statements_and_handler_structure() {
    let text = concat!(
        "def parse(value):\n",
        "    try:\n",
        "        return validate(value)\n",
        "    except ValidationError:\n",
        "        return None\n",
    );
    let fact = fact(
        crate::discovery::Document {
            relative: "parser.py".to_string(),
            source: text.to_string(),
        },
        try_blocks,
    );
    let region = &fact["regions"][0];

    assert_eq!(
        region["protected_statements"][0]["text"],
        "return validate(value)"
    );
    assert_eq!(region["handlers"][0]["caught"], "ValidationError");
    assert_eq!(region["handlers"][0]["caught_is_tuple"], false);
    assert_eq!(region["handlers"][0]["alias"], "");
    assert_eq!(region["handlers"][0]["body"][0]["text"], "return None");
    assert_eq!(region["has_else"], false);
    assert_eq!(region["has_finally"], false);
    assert_eq!(region["is_exception_group"], false);
}
