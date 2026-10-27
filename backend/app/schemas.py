from typing import Any, Optional
from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field, field_validator,model_validator

class ToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = False
    default: Optional[Any] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        allowed_types = {
            "string",
            "integer",
            "number",
            "boolean",
            "object",
            "array",
            "null",
        }

        if value not in allowed_types:
            raise ValueError(
                f"Invalid JSON Schema type: {value}"
            )

        return value

class ToolReturn(BaseModel):
    type: str
    description: str
    return_schema: dict[str, Any] = Field(
        default_factory=dict,
        alias="schema"
    )


class ToolContract(BaseModel):
    name: str
    description: str
    version: str = "v1"
    parameters: list[ToolParameter] = Field(default_factory=list)
    required: list[str] = Field(default_factory=list)
    returns: ToolReturn

    @model_validator(mode="after")
    def validate_contract(self):
        parameter_names = [parameter.name for parameter in self.parameters]

        # Check for duplicate parameter names
        if len(parameter_names) != len(set(parameter_names)):
            raise ValueError("Parameter names must be unique")

        # Check that required parameters exist
        unknown_required = set(self.required) - set(parameter_names)

        if unknown_required:
            raise ValueError(
                f"Required parameters not defined: {sorted(unknown_required)}"
            )

        # Check that required list matches parameter.required
        for parameter in self.parameters:
            if parameter.required and parameter.name not in self.required:
                raise ValueError(
                    f"Parameter '{parameter.name}' is marked required "
                    "but is missing from the required list"
                )

        return self

class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    data: Optional[dict[str, Any]] = None

class ToolSchema:
    def __init__(self, contract: ToolContract):
        self.contract = contract
    def generate_json_schema(self) -> dict:
        properties = {}

        for parameter in self.contract.parameters:
            properties[parameter.name] = {
                "type": parameter.type,
                "description": parameter.description,
            }

            if parameter.default is not None:
                properties[parameter.name]["default"] = parameter.default

        return {
            "name": self.contract.name,
            "description": self.contract.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": self.contract.required,
            },
        }

    def validate_input(
    self,
    input_data: dict[str, Any],
) -> ValidationResult:
        data = dict(input_data)

        for parameter in self.contract.parameters:
            if parameter.name not in data and parameter.default is not None:
                data[parameter.name] = parameter.default

        schema = self.generate_json_schema()["parameters"]

        validator = Draft202012Validator(schema)
        errors = sorted(
            validator.iter_errors(data),
            key=lambda error: list(error.path),
        )

        if errors:
            return ValidationResult(
                valid=False,
                errors=[error.message for error in errors],
            )

        return ValidationResult(
            valid=True,
            data=data,
        )

    def generate_openapi_schema(self) -> dict:
        json_schema = self.generate_json_schema()

        return {
            "name": json_schema["name"],
            "description": json_schema["description"],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": json_schema["parameters"]
                    }
                }
            },
            "responses": {
                "200": {
                    "description": self.contract.returns.description,
                    "content": {
                        "application/json": {
                            "schema": self.contract.returns.return_schema
                        }
                    }
                }
            }
        }

    def get_tool_signature(self) -> str:
        parameters = []

        for parameter in self.contract.parameters:
            required = "required" if parameter.required else "optional"
            parameters.append(
                f"{parameter.name}: {parameter.type} "
                f"({required}) - {parameter.description}"
            )

        parameter_text = ", ".join(parameters)

        return (
            f"{self.contract.name}({parameter_text}) "
            f"-> {self.contract.returns.type}: "
            f"{self.contract.returns.description}"
        )