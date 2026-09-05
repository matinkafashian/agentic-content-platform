from pydantic import BaseModel, ConfigDict, Field, field_validator


class SupportKnowledgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(default="", max_length=100_000)

    @field_validator("content", mode="before")
    @classmethod
    def normalize_content(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value
