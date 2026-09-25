"""MCP tools for querying InvenTree StockItem data."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from ..mcp_server import mcp
from ..proxy import call_view
from ..view_resolution import resolve_view
from ._common import build_query_params


@mcp.tool()
async def list_stock_items(
    part: int | None = None,
    location: int | None = None,
    in_stock: bool | None = None,
    ordering: str | None = None,
    filters: dict[str, Any] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List stock items.

    Returns a paginated envelope: {count, next, previous, results}. Each
    entry in `results` has the same shape as get_stock_item's return value -
    use its `pk` field with get_stock_item to fetch full detail for one of
    them.

    Args:
        part: restrict to stock of this Part ID (includes variants of the part).
        location: restrict to stock held at this StockLocation ID.
        in_stock: True for only items that are actually usable right now -
            quantity > 0, not allocated to a sales order/customer/build, not
            currently mid-build, and in an "available" status (excludes e.g.
            rejected/destroyed/lost stock). False for the inverse. Omit to
            include both.
        ordering: field to sort results by, e.g. "-quantity" for highest
            quantity first ('-' prefix for descending, omit it for
            ascending). Combine with limit to get a "top N by X" result, e.g.
            ordering="-quantity", limit=5 for the 5 largest stock items. Call
            describe_filters("stock") and check its ordering_fields list for
            valid values - an unrecognized field is silently ignored (no
            error, no sort) rather than rejected.
        filters: additional filter parameters beyond the named arguments
            above - call describe_filters("stock") to see what's available,
            e.g. filters={"low_stock": true}.
        limit: maximum number of results to return - defaults to 100 (the
            maximum) to minimize round trips for large result sets; pass a
            smaller value to page through results in smaller batches.
        offset: pagination offset.
    """
    base: dict[str, Any] = {}
    if part is not None:
        base["part"] = part
    if location is not None:
        base["location"] = location
    if in_stock is not None:
        base["in_stock"] = in_stock
    if ordering is not None:
        base["ordering"] = ordering

    params = build_query_params(base, filters, limit, offset)

    return await call_view(
        resolve_view("stock.api", "StockList"),
        "GET",
        "/api/stock/",
        query_params=params,
    )


@mcp.tool()
async def get_stock_item(
    stock_item_id: int, filters: dict[str, Any] | None = None
) -> dict:
    """Get full detail for a single stock item by its ID.

    Returns the same object shape as one entry in list_stock_items's
    `results` array. Get a valid ID from list_stock_items (its `pk` field)
    if you don't already have one.

    Args:
        stock_item_id: the StockItem's database ID.
        filters: optional-field toggles beyond what's returned by default -
            call describe_filters("stock") and check its optional_fields,
            e.g. filters={"tests": true} to include test results inline.

    Raises:
        ToolError: no stock item exists with that ID, or the caller doesn't
            have permission to view it.
    """
    return await call_view(
        resolve_view("stock.api", "StockDetail"),
        "GET",
        f"/api/stock/{stock_item_id}/",
        pk=stock_item_id,
        query_params=filters,
    )


@mcp.tool()
async def create_stock_item(
    part: int,
    quantity: float = 1,
    location: int | None = None,
    serial_numbers: str | None = None,
    batch: str | None = None,
    status: int | None = None,
    notes: str | None = None,
    purchase_price: float | None = None,
) -> dict:
    """Create stock for a part: one item, or one item per serial number.

    A write: blocked while the plugin's Read Only setting is on, and needs
    the stock add permission.

    Args:
        part: the Part ID to create stock for.
        quantity: quantity. With serial numbers it must equal their count.
        location: StockLocation ID, or omit for no location.
        serial_numbers: serials for a trackable part, e.g. "1001",
            "1001,1002" or "1001-1005". Each becomes its own stock item.
            (InvenTree's create API takes serials only through this field;
            a plain `serial` is ignored on create.)
        batch: batch code.
        status: stock status code (10 = OK); see describe_filters("stock").
        notes: notes for the new stock.
        purchase_price: unit purchase price.

    Returns:
        {"items": [...]}, the created stock items, each shaped like
        get_stock_item.
    """
    fields = {
        "location": location,
        "serial_numbers": serial_numbers,
        "batch": batch,
        "status": status,
        "notes": notes,
        "purchase_price": purchase_price,
    }
    data: dict[str, Any] = {"part": part, "quantity": quantity}
    data.update({k: v for k, v in fields.items() if v is not None})
    result = await call_view(
        resolve_view("stock.api", "StockList"), "POST", "/api/stock/", data=data
    )
    return {"items": result if isinstance(result, list) else [result]}


async def _adjust(view_name: str, path: str, data: dict[str, Any]) -> dict:
    await call_view(resolve_view("stock.api", view_name), "POST", path, data=data)
    return {"ok": True}


@mcp.tool()
async def adjust_stock(stock_item_id: int, quantity: float, notes: str = "") -> dict:
    """Add stock to, or take stock from, a stock item.

    A write: blocked while the plugin's Read Only setting is on, and needs
    the stock change permission. Recorded in the item's history under the
    calling user.

    Args:
        stock_item_id: the StockItem ID.
        quantity: amount to add (positive) or remove (negative).
        notes: note for the history entry.
    """
    if quantity == 0:
        raise ToolError("quantity must not be zero")
    view, path = ("StockAdd", "/api/stock/add/") if quantity > 0 else ("StockRemove", "/api/stock/remove/")
    await _adjust(view, path, {"items": [{"pk": stock_item_id, "quantity": abs(quantity)}], "notes": notes})
    return await get_stock_item(stock_item_id)


@mcp.tool()
async def count_stock(stock_item_id: int, quantity: float, notes: str = "") -> dict:
    """Record a stocktake: set a stock item's counted, absolute quantity.

    A write: blocked while the plugin's Read Only setting is on, and needs
    the stock change permission.

    Args:
        stock_item_id: the StockItem ID.
        quantity: the counted quantity.
        notes: note for the history entry.
    """
    await _adjust(
        "StockCount", "/api/stock/count/", {"items": [{"pk": stock_item_id, "quantity": quantity}], "notes": notes}
    )
    return await get_stock_item(stock_item_id)


@mcp.tool()
async def transfer_stock(
    stock_item_id: int, location: int, quantity: float | None = None, notes: str = ""
) -> dict:
    """Move a stock item (or part of it) to another location.

    A write: blocked while the plugin's Read Only setting is on, and needs
    the stock change permission. Moving part of an item splits it.

    Args:
        stock_item_id: the StockItem ID.
        location: destination StockLocation ID.
        quantity: how much to move; omit to move the whole item.
        notes: note for the history entry.
    """
    if quantity is None:
        quantity = float((await get_stock_item(stock_item_id))["quantity"])
    await _adjust(
        "StockTransfer",
        "/api/stock/transfer/",
        {"items": [{"pk": stock_item_id, "quantity": quantity}], "location": location, "notes": notes},
    )
    return await get_stock_item(stock_item_id)


@mcp.tool()
async def update_stock_item(
    stock_item_id: int,
    status: int | None = None,
    batch: str | None = None,
    serial: str | None = None,
    expiry_date: str | None = None,
    packaging: str | None = None,
    notes: str | None = None,
    link: str | None = None,
    purchase_price: float | None = None,
) -> dict:
    """Change fields of a stock item. Only the fields you pass change.

    Quantity and location change through adjust_stock, count_stock and
    transfer_stock, so they're recorded as stock movements.

    A write: blocked while the plugin's Read Only setting is on, and needs
    the stock change permission.

    Args:
        stock_item_id: the StockItem ID.
        status: stock status code (e.g. 10 OK, 50 attention, 55 damaged,
            60 destroyed, 65 rejected, 70 lost); see describe_filters("stock").
        batch: batch code.
        serial: serial number.
        expiry_date: expiry date, YYYY-MM-DD.
        packaging: packaging description.
        notes: notes (markdown).
        link: external link (URL).
        purchase_price: unit purchase price.
    """
    fields = {
        "status": status,
        "batch": batch,
        "serial": serial,
        "expiry_date": expiry_date,
        "packaging": packaging,
        "notes": notes,
        "link": link,
        "purchase_price": purchase_price,
    }
    data = {k: v for k, v in fields.items() if v is not None}
    if not data:
        raise ToolError("Pass at least one field to change")
    return await call_view(
        resolve_view("stock.api", "StockDetail"), "PATCH", f"/api/stock/{stock_item_id}/", pk=stock_item_id, data=data
    )
