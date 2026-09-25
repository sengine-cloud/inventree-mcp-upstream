"""MCP tools for scanning and assigning barcodes."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from ..mcp_server import mcp
from ..proxy import call_view
from ..view_resolution import resolve_view

# Model keys accepted by /api/barcode/link/ and /api/barcode/unlink/.
LINKABLE_MODELS = (
    "build",
    "manufacturerpart",
    "part",
    "purchaseorder",
    "returnorder",
    "salesorder",
    "salesordershipment",
    "stockitem",
    "stocklocation",
    "supplierpart",
    "transferorder",
)


def _check_model(model: str) -> None:
    if model not in LINKABLE_MODELS:
        raise ToolError(f"model must be one of: {', '.join(LINKABLE_MODELS)}")


@mcp.tool()
async def scan_barcode(barcode: str) -> dict:
    """Resolve scanned barcode data to the InvenTree object it identifies.

    Every active barcode plugin is tried, so InvenTree's own barcodes and
    plugin-specific formats (e.g. label short links) both resolve. Barcode
    data is case-sensitive. Goes through a POST endpoint, so it is blocked
    while the plugin's Read Only setting is on.

    Returns the match (e.g. {"stockitem": {"pk": ..., "instance": {...}},
    "plugin": ...}), or {"match": false, ...} when nothing matched.

    Args:
        barcode: the raw scanned barcode text.
    """
    try:
        return await call_view(
            resolve_view("plugin.base.barcodes.api", "BarcodeScan"),
            "POST",
            "/api/barcode/",
            data={"barcode": barcode},
        )
    except ToolError as exc:
        if "No match found" in str(exc):
            return {"match": False, "barcode_data": barcode, "error": str(exc)}
        raise


@mcp.tool()
async def link_barcode(barcode: str, model: str, object_id: int) -> dict:
    """Assign a third-party barcode to an InvenTree object.

    A write: blocked while the plugin's Read Only setting is on, and needs
    change permission on that object's type.

    Args:
        barcode: the raw barcode text to assign.
        model: one of build, manufacturerpart, part, purchaseorder,
            returnorder, salesorder, salesordershipment, stockitem,
            stocklocation, supplierpart, transferorder.
        object_id: the object's database ID.
    """
    _check_model(model)
    data: dict[str, Any] = {"barcode": barcode, model: object_id}
    return await call_view(
        resolve_view("plugin.base.barcodes.api", "BarcodeAssign"),
        "POST",
        "/api/barcode/link/",
        data=data,
    )


@mcp.tool()
async def unlink_barcode(model: str, object_id: int) -> dict:
    """Remove the third-party barcode assigned to an InvenTree object.

    A write: blocked while the plugin's Read Only setting is on.

    Args:
        model: object type, as for link_barcode.
        object_id: the object's database ID.
    """
    _check_model(model)
    return await call_view(
        resolve_view("plugin.base.barcodes.api", "BarcodeUnassign"),
        "POST",
        "/api/barcode/unlink/",
        data={model: object_id},
    )
