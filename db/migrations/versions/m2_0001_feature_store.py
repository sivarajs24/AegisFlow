"""M2: feature store support - unique edge index, graph snapshots, known fraud.

Revision ID: m2_0001
Revises: 
"""
import sqlalchemy as sa
from alembic import op

revision = "m2_0001"
down_revision = None
branch_labels = None
depends_on = None

EDGE_KEY = "src_type, src_id, dst_type, dst_id, edge_type"

def upgrade():
    # 0. Create entity_edges if not already created in M1
    op.execute("""
        CREATE TABLE IF NOT EXISTS entity_edges (
            id BIGSERIAL PRIMARY KEY,
            src_type VARCHAR(16) NOT NULL,
            src_id UUID NOT NULL,
            dst_type VARCHAR(16) NOT NULL,
            dst_id UUID NOT NULL,
            edge_type VARCHAR(32) NOT NULL,
            first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            weight INT NOT NULL DEFAULT 1
        )
    """)

    # 1. Merge duplicate edges M1 may have written, so the unique index can be built.
    op.execute(f"""
        UPDATE entity_edges k SET weight = d.total, first_seen = d.first
        FROM (SELECT min(id) AS keep_id, sum(weight) AS total, min(first_seen) AS first
              FROM entity_edges GROUP BY {EDGE_KEY} HAVING count(*) > 1) d
        WHERE k.id = d.keep_id""")

    op.execute(f"""
        DELETE FROM entity_edges a USING entity_edges b
        WHERE a.id > b.id AND (a.src_type, a.src_id, a.dst_type, a.dst_id, a.edge_type) 
            = (b.src_type, b.src_id, b.dst_type, b.dst_id, b.edge_type)""")

    op.create_index("uq_entity_edges_key", "entity_edges", 
                    ["src_type", "src_id", "dst_type", "dst_id", "edge_type"], unique=True)

    # 2. Point-in-time graph features (Decision D7).
    op.create_table(
        "graph_feature_snapshots",
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("component_size", sa.Integer(), nullable=False),
        sa.Column("dist_to_fraud", sa.Integer(), nullable=False),
        sa.Column("risk_rank", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("entity_id", "computed_at"),
    )
    op.create_index("ix_graph_snapshots_time", "graph_feature_snapshots", ["computed_at"])

    # 3. Known fraud used to seed graph features (Decision D5).
    op.create_table(
        "known_fraud_entities",
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("entity_type", "entity_id"),
    )


def downgrade():
    op.drop_table("known_fraud_entities")
    op.drop_index("ix_graph_snapshots_time", table_name="graph_feature_snapshots")
    op.drop_table("graph_feature_snapshots")
    op.drop_index("uq_entity_edges_key", table_name="entity_edges")
