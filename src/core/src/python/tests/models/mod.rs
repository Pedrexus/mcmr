use super::*;

#[test]
fn pydantic_validator_evidence_is_derived_from_its_body_and_decorator() {
    let facts = facts_for(
        concat!(
            "from pydantic import BaseModel, field_validator, model_validator\n\n",
            "class Credential(BaseModel):\n",
            "    token: str | None = None\n",
            "    username: str | None = None\n",
            "    password: Optional[str] = None\n\n",
            "    @field_validator('token')\n",
            "    @classmethod\n",
            "    def normalized(cls, value):\n",
            "        if len(value) < 2:\n",
            "            raise ValueError('short')\n",
            "        return value.strip()\n\n",
            "    @model_validator(mode='after')\n",
            "    def one_variant(self):\n",
            "        variants = sum((self.token is not None, ",
            "self.username is not None or self.password is not None))\n",
            "        if variants > 1:\n",
            "            raise ValueError('choose one')\n",
            "        return self\n",
        ),
        FactFamily("PydanticModelFact"),
    );
    let validators = facts[0]["models"][0]["validators"].as_array().unwrap();

    assert_eq!(validators[0]["kind"], "field");
    assert_eq!(validators[0]["declarative_constraint_count"], 2);
    assert_eq!(validators[1]["kind"], "model_after");
    assert_eq!(
        validators[1]["fields_read"],
        json!(["password", "token", "username"])
    );
    assert_eq!(validators[1]["has_self_call"], false);
    assert_eq!(validators[1]["has_nonfield_access"], false);
    assert_eq!(validators[1]["proves_disjoint_optional_variants"], true);
    assert_eq!(validators[1]["variant_count"], 2);
}

#[test]
fn pydantic_variant_evidence_follows_a_local_value_tuple() {
    let facts = facts_for(
        concat!(
            "from pydantic import BaseModel, model_validator\n\n",
            "class Credential(BaseModel):\n",
            "    token: str | None = None\n",
            "    username: str | None = None\n",
            "    certificate: bytes | None = None\n\n",
            "    @model_validator(mode='after')\n",
            "    def one_variant(self):\n",
            "        variants = (self.token, self.username, self.certificate)\n",
            "        if sum(value is not None for value in variants) > 1:\n",
            "            raise ValueError('choose one')\n",
            "        return self\n",
        ),
        FactFamily("PydanticModelFact"),
    );
    let validator = &facts[0]["models"][0]["validators"][0];

    assert_eq!(validator["proves_disjoint_optional_variants"], true);
    assert_eq!(validator["variant_count"], 3);
}

#[test]
fn pydantic_fields_distinguish_variadic_tuples_from_fixed_records() {
    let facts = facts_for(
        concat!(
            "from pydantic import BaseModel as Schema\n",
            "from typing import ClassVar as Fixed, Tuple as Items\n\n",
            "class Profile(Schema):\n",
            "    tags: Items[str, ...]\n",
            "    point: tuple[int, int]\n",
            "    groups: list[tuple[str, ...]]\n\n",
            "    registry: Fixed[tuple[str, ...]] = ()\n\n",
            "class Plain:\n",
            "    tags: tuple[str, ...]\n",
        ),
        FactFamily("PydanticModelFact"),
    );
    let models = facts[0]["models"].as_array().unwrap();
    let profile = models
        .iter()
        .find(|model| model["name"] == "Profile")
        .unwrap();
    let fields = profile["fields"].as_array().unwrap();

    assert_eq!(
        json!([
            profile["is_pydantic_model"],
            fields.len(),
            fields[0]["contains_variadic_tuple"],
            fields[1]["contains_variadic_tuple"],
            fields[2]["contains_variadic_tuple"],
            fields[0]["span"]["start_line"],
        ]),
        json!([true, 3, true, false, true, 5])
    );
    assert_eq!(
        models
            .iter()
            .find(|model| model["name"] == "Plain")
            .unwrap()["is_pydantic_model"],
        false
    );
}

#[test]
fn pydantic_models_locate_an_explicit_flexible_foundation() {
    let facts = facts_for(
        concat!(
            "from patos import FrozenFlexModel as Flexible, FrozenModel\n\n",
            "class Catalog(Flexible):\n",
            "    modules: list[str]\n\n",
            "class Policy(FrozenModel):\n",
            "    name: str\n",
        ),
        FactFamily("PydanticModelFact"),
    );
    let models = facts[0]["models"].as_array().unwrap();

    assert_eq!(models[0]["uses_flexible_model"], true);
    assert_eq!(models[0]["flexible_base_span"]["start_line"], 3);
    assert_eq!(models[1]["uses_flexible_model"], false);
    assert_eq!(models[1]["flexible_base_span"], Value::Null);
}

#[test]
fn malformed_validators_do_not_gain_invented_receiver_or_value_names() {
    let facts = facts_for(
        concat!(
            "from pydantic import BaseModel, field_validator, model_validator\n\n",
            "class Credential(BaseModel):\n",
            "    token: str\n\n",
            "    @field_validator('token')\n",
            "    def normalized():\n",
            "        return value.strip()\n\n",
            "    @model_validator(mode='after')\n",
            "    def checked():\n",
            "        return self.token\n",
        ),
        FactFamily("PydanticModelFact"),
    );
    let validators = facts[0]["models"][0]["validators"].as_array().unwrap();

    assert_eq!(validators[0]["declarative_constraint_count"], 0);
    assert_eq!(validators[1]["fields_read"], json!([]));
}

#[test]
fn pydantic_variant_proof_rejects_lookalikes() {
    let facts = facts_for(
        concat!(
            "from pydantic import BaseModel, model_validator\n\n",
            "class Credential(BaseModel):\n",
            "    token: str | None = None\n",
            "    username: str | None = None\n",
            "    required: str\n\n",
            "    @model_validator(mode='before')\n",
            "    def wrong_mode(self):\n",
            "        if sum((self.token is not None, self.username is not None)) > 1:\n",
            "            raise ValueError('choose one')\n\n",
            "    @model_validator(mode='after')\n",
            "    def wrong_limit(self):\n",
            "        if sum((self.token is not None, self.username is not None)) > 2:\n",
            "            raise ValueError('choose one')\n\n",
            "    @model_validator(mode='after')\n",
            "    def overlapping(self):\n",
            "        if sum((self.token is not None, ",
            "self.token is not None or self.username is not None)) > 1:\n",
            "            raise ValueError('choose one')\n\n",
            "    @model_validator(mode='after')\n",
            "    def not_optional(self):\n",
            "        if sum((self.token is not None, self.required is not None)) > 1:\n",
            "            raise ValueError('choose one')\n\n",
            "    @model_validator(mode='after')\n",
            "    def shadowed(self, sum):\n",
            "        if sum((self.token is not None, self.username is not None)) > 1:\n",
            "            raise ValueError('choose one')\n",
        ),
        FactFamily("PydanticModelFact"),
    );
    let validators = facts[0]["models"][0]["validators"].as_array().unwrap();

    assert_eq!(validators[0]["kind"], "other");
    assert_eq!(validators[0]["proves_disjoint_optional_variants"], true);
    assert!(
        validators[1..]
            .iter()
            .all(|validator| validator["proves_disjoint_optional_variants"] == false)
    );
}
