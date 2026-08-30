from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.brand.schemas import normalize_hashtag

ContentAngle = Literal[
    "product_intro",
    "educational",
    "faq",
    "problem_solution",
    "trust",
    "order_guide",
]


def _unique_text(values: list[str]) -> list[str]:
    normalized = [value.strip() for value in values if value.strip()]
    return list(dict.fromkeys(normalized))


def _unique_hashtags(values: list[str]) -> list[str]:
    normalized = [normalize_hashtag(value) for value in values]
    return list(dict.fromkeys(value for value in normalized if value))


class ProductFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=4000)
    price: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    availability: str = Field(default="available", max_length=40)
    shipping_info: str = Field(default="", max_length=1000)
    attributes: dict[str, str] = Field(default_factory=dict, max_length=30)
    tags: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("name", "description", "availability", "shipping_info", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("attributes")
    @classmethod
    def normalize_attributes(cls, values: dict[str, str]) -> dict[str, str]:
        return {
            key.strip(): value.strip()
            for key, value in values.items()
            if key.strip() and value.strip()
        }

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        return _unique_hashtags(values)


class BrandFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_name: str = Field(min_length=2, max_length=200)
    tagline: str = Field(default="", max_length=500)
    audience: str = Field(default="", max_length=500)
    tone_guidelines: str = Field(default="", max_length=2000)
    support_handle: str = Field(min_length=4, max_length=65)
    default_cta: str = Field(min_length=2, max_length=500)
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

    @field_validator("approved_claims")
    @classmethod
    def normalize_claims(cls, values: list[str]) -> list[str]:
        return _unique_text(values)

    @field_validator("default_hashtags")
    @classmethod
    def normalize_hashtags(cls, values: list[str]) -> list[str]:
        return _unique_hashtags(values)


class ContentGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: ProductFacts
    brand: BrandFacts
    user_brief: str = Field(min_length=10, max_length=2000)
    requested_angle: ContentAngle

    @field_validator("user_brief", mode="before")
    @classmethod
    def strip_brief(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class GeneratedContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=2, max_length=300)
    body: str = Field(min_length=2, max_length=3000)
    benefits: list[str] = Field(min_length=1, max_length=5)
    cta: str = Field(min_length=2, max_length=500)
    hashtags: list[str] = Field(default_factory=list, max_length=6)
    used_emojis: list[str] = Field(default_factory=list, max_length=6)
    content_angle: ContentAngle

    @field_validator("headline", "body", "cta", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("benefits", "used_emojis")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _unique_text(values)

    @field_validator("hashtags")
    @classmethod
    def normalize_hashtags(cls, values: list[str]) -> list[str]:
        return _unique_hashtags(values)

