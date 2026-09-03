"""Prevent duplicate delivery for the same bundle, platform, and destination."""

from collections import defaultdict
from collections.abc import Sequence
from hashlib import sha256

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0004"
down_revision: str | Sequence[str] | None = "20260831_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _delivery_key(bundle_id: int, platform: str, destination: str) -> str:
    identity = f"{bundle_id}\x1f{platform}\x1f{destination}"
    return sha256(identity.encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.add_column(
        "publications",
        sa.Column("delivery_key", sa.String(length=64), nullable=True),
    )
    connection = op.get_bind()
    publications = sa.table(
        "publications",
        sa.column("id", sa.Integer()),
        sa.column("bundle_id", sa.Integer()),
        sa.column("platform", sa.String()),
        sa.column("destination", sa.String()),
        sa.column("status", sa.String()),
        sa.column("delivery_key", sa.String()),
    )
    grouped: dict[tuple[int, str, str], list[dict[str, object]]] = defaultdict(list)
    rows = connection.execute(
        sa.select(
            publications.c.id,
            publications.c.bundle_id,
            publications.c.platform,
            publications.c.destination,
            publications.c.status,
        ).order_by(publications.c.id)
    ).mappings()
    for row in rows:
        identity = (
            int(row["bundle_id"]),
            str(row["platform"]),
            str(row["destination"]),
        )
        grouped[identity].append(dict(row))

    for identity, candidates in grouped.items():
        successful = [item for item in candidates if item["status"] == "succeeded"]
        canonical = successful[0] if successful else candidates[0]
        connection.execute(
            sa.update(publications)
            .where(publications.c.id == canonical["id"])
            .values(delivery_key=_delivery_key(*identity))
        )

    op.create_index(
        "ix_publications_delivery_key",
        "publications",
        ["delivery_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_publications_delivery_key", table_name="publications")
    op.drop_column("publications", "delivery_key")
