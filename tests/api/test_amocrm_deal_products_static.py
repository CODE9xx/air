from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AMO = ROOT / "packages/crm-connectors/src/crm_connectors/amocrm.py"
CRM_PULL = ROOT / "apps/worker/worker/jobs/crm_pull.py"
TENANT_MODELS = ROOT / "apps/api/app/db/models/tenant_schema.py"
TENANT_MIGRATION = ROOT / "apps/api/app/db/migrations/tenant/versions/0003_deal_products.py"


def test_amocrm_deal_fetch_requests_linked_catalog_elements_and_source() -> None:
    source = AMO.read_text(encoding="utf-8")

    assert "contacts,companies,catalog_elements,source" in source
    assert "_embedded.source" in source


def test_tenant_schema_has_deal_product_link_table() -> None:
    source = TENANT_MODELS.read_text(encoding="utf-8")
    migration = TENANT_MIGRATION.read_text(encoding="utf-8")

    assert "class DealProduct" in source
    assert '__tablename__ = "deal_products"' in source
    assert "PrimaryKeyConstraint(\"deal_id\", \"external_id\"" in source
    assert "revision: str = \"0003_deal_products\"" in migration
    assert "CREATE TABLE IF NOT EXISTS deal_products" in migration
    assert "CREATE INDEX IF NOT EXISTS ix_deal_products_product" in migration


def test_worker_syncs_deal_catalog_elements_into_deal_products() -> None:
    source = CRM_PULL.read_text(encoding="utf-8")

    assert "_catalog_element_external_id" in source
    assert "_sync_deal_products" in source
    assert "_link_deal_products_to_products" in source
    assert "embedded.get(\"catalog_elements\")" in source
    assert "deal_products_linked" in source
