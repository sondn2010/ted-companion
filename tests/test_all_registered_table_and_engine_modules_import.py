"""Mọi TABLE_MODULES / ENGINE_CLASSES import được; create_all trên SQLite sạch ra đúng tên bảng."""
import importlib

from sqlalchemy import inspect
from sqlmodel import SQLModel, create_engine

from src.core.register_all_table_models import TABLE_MODULES
from src.modules_runtime.module_engine_base_and_factory import ENGINE_CLASSES, ModuleEngineBase

EXPECTED_TABLES = {
    "task", "focussession", "dailyjournal", "appstatekv", "rock", "calendareventcache",
    "quizitem", "reviewstate", "attempt", "plansnapshot", "agendadone", "writingsubmission", "progressreportoutbox",
}


def test_every_table_module_imports():
    for name in TABLE_MODULES:
        assert importlib.import_module(name) is not None, name


def test_every_engine_class_path_resolves_to_engine_base_subclass():
    for engine_name, path in ENGINE_CLASSES.items():
        module_name, _, class_name = path.partition(":")
        cls = getattr(importlib.import_module(module_name), class_name)
        assert issubclass(cls, ModuleEngineBase), engine_name


def test_create_all_on_fresh_sqlite_yields_expected_tables():
    import src.core.models  # noqa: F401  (đăng ký bảng gốc + TABLE_MODULES)
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    names = {n.lower() for n in inspect(engine).get_table_names()}
    assert EXPECTED_TABLES <= names, EXPECTED_TABLES - names
    engine.dispose()
