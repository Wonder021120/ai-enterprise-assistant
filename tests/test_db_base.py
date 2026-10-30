from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase

from app.db.base import Base, NAMING_CONVENTION


def test_base_can_be_imported():
    assert Base is not None
    assert NAMING_CONVENTION is not None


def test_base_uses_sqlalchemy_declarative_base():
    assert issubclass(Base, DeclarativeBase)
    assert isinstance(Base.metadata, MetaData)


def test_base_metadata_uses_expected_naming_convention():
    assert dict(Base.metadata.naming_convention) == NAMING_CONVENTION


def test_constraint_and_index_names_follow_convention():
    parent_table = Table(
        "base_test_parent",
        Base.metadata,
        Column("id", Integer, primary_key=True),
        Column("code", String(50), nullable=False),
        UniqueConstraint("code"),
        CheckConstraint("length(code) > 0", name="code_nonempty"),
    )
    child_table = Table(
        "base_test_child",
        Base.metadata,
        Column("id", Integer, primary_key=True),
        Column(
            "parent_id",
            Integer,
            ForeignKey("base_test_parent.id"),
            nullable=False,
        ),
    )
    code_index = Index(None, parent_table.c.code)

    try:
        unique_constraint = next(
            constraint
            for constraint in parent_table.constraints
            if isinstance(constraint, UniqueConstraint)
        )
        check_constraint = next(
            constraint
            for constraint in parent_table.constraints
            if isinstance(constraint, CheckConstraint)
        )
        foreign_key_constraint = next(
            iter(child_table.foreign_key_constraints)
        )

        assert parent_table.primary_key.name == "pk_base_test_parent"
        assert child_table.primary_key.name == "pk_base_test_child"
        assert unique_constraint.name == "uq_base_test_parent_code"
        assert check_constraint.name == (
            "ck_base_test_parent_code_nonempty"
        )
        assert foreign_key_constraint.name == (
            "fk_base_test_child_parent_id_base_test_parent"
        )
        assert code_index.name == "ix_base_test_parent_code"
    finally:
        Base.metadata.remove(child_table)
        Base.metadata.remove(parent_table)
