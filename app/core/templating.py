from pathlib import Path

from fastapi.templating import Jinja2Templates


def fa_digits(value: object) -> str:
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
templates.env.filters["fa_digits"] = fa_digits
