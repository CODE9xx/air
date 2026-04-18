"""
Placeholder: все ORM-модели main-schema (public) объявлены в
``apps/api/app/db/models/__init__.py``.

История: зона BE+DW (см. ``docs/architecture/FILE_OWNERSHIP.md``), классы уже
собраны в ``__init__.py`` для совместимости существующих импортов. Этот файл
сохранён на случай будущего декомпозирования по доменам — держим пустым,
чтобы избежать дублирующих регистраций в ``MainBase.metadata``.

Если хочется импортировать явно по модулю — используйте:
    from app.db.models import User, Workspace, ...  # каноничный импорт
"""
