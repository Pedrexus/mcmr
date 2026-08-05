"""Nightly rollups the ecommerce warehouse runs against its DataHub-governed assets."""

_REVENUE = "SELECT order_id, legacy_total FROM ecommerce.analytics.orders"

_INVOICES = "SELECT invoice_id, CAST(amount AS STRING) FROM ecommerce.marts.invoices"
