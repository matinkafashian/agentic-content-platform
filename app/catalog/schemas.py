from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=200)
    description: str = ""
    price: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    availability: str = Field(default="available", max_length=40)
    shipping_info: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=30)
    active: bool = True

    @field_validator("name", "description", "availability", "shipping_info", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    availability: str | None = Field(default=None, max_length=40)
    shipping_info: str | None = None
    attributes: dict[str, str] | None = None
    tags: list[str] | None = Field(default=None, max_length=30)
    active: bool | None = None

    @field_validator("name", "description", "availability", "shipping_info", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class ProductRead(ProductCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    primary_image_path: str | None
