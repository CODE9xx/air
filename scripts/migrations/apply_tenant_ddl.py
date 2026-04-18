"""
CLI-обёртка: применить tenant-DDL к указанной schema.

Алиас для ``apply_tenant_template`` с именем, совпадающим с Brief 3
(``apply_tenant_ddl.py``). В implementation'е мы используем полноценный
alembic-путь (см. ``apply_tenant_template.py`` и ``docs/db/MIGRATION_STRATEGY.md``).

Использование:
    python -m scripts.migrations.apply_tenant_ddl <schema_name>
    python -m scripts.migrations.apply_tenant_ddl crm_amo_abc12345
"""
from __future__ import annotations

import sys

from scripts.migrations.apply_tenant_template import (
    apply_tenant_template,
    drop_tenant_schema,
)


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: python -m scripts.migrations.apply_tenant_ddl <schema_name> "
            "[--drop]",
            file=sys.stderr,
        )
        return 2

    schema = sys.argv[1]
    drop = "--drop" in sys.argv[2:]

    if drop:
        drop_tenant_schema(schema)
        print(f"[apply_tenant_ddl] DROP OK schema={schema}")
        return 0

    apply_tenant_template(schema)
    print(f"[apply_tenant_ddl] UPGRADE OK schema={schema}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
