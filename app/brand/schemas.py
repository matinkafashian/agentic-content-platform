import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

HANDLE_PATTERN = re.compile(r"^@[A-Za-z0-9_]{3,64}$")


def normalize_hashtag(value: str) -> str:
    normalized = "_".join(value.strip().removeprefix("#").split())
    return normalized.strip("_")


def normalize_handle(value: str) -> str:
    normalized = value.strip()
    if normalized and not normalized.startswith("@"):
        normalized = f"@{normalized}"
    return normalized


class BrandProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_name: str = Field(min_length=2, max_length=200)
    tagline: str = Field(default="", max_length=500)
    audience: str = Field(default="", max_length=500)
    tone_guidelines: str = Field(default="", max_length=2000)
    support_handle: str = Field(min_length=4, max_length=65)
    default_cta: str = Field(default="", max_length=500)
    approved_claims: list[str] = Field(default_factory=list, max_length=20)
    default_hashtags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator(
        "business_name",
        "tagline",
        "audience",
        "tone_guidelines",
        "support_handle",
        "default_cta",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("support_handle")
    @classmethod
    def valid_support_handle(cls, value: str) -> str:
        normalized = normalize_handle(value)
        if not HANDLE_PATTERN.fullmatch(normalized):
            raise ValueError("support handle must contain only latin letters, numbers, or _")
        return normalized

    @field_validator("approved_claims")
    @classmethod
    def normalize_claims(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        return list(dict.fromkeys(normalized))

    @field_validator("default_hashtags")
    @classmethod
    def normalize_hashtags(cls, values: list[str]) -> list[str]:
        normalized = [normalize_hashtag(value) for value in values]
        return list(dict.fromkeys(value for value in normalized if value))

