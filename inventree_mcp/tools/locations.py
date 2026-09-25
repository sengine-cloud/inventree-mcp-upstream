"""MCP tools for querying InvenTree StockLocation data."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from ..mcp_server import mcp
from ..proxy import call_view
from ..view_resolution import resolve_view
from ._common import build_query_params, clamp_limit


@mcp.tool()
async def list_locations(
    search: str | None = None,
    parent: int | None = None,
    ordering: str | None = None,
    filters: dict[str, Any] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List stock locations.

    Returns a paginated envelope: {count, next, previous, results}. Each
    entry in `results` has the same shape as get_location's return value -
    use its `pk` field with get_location to fetch full detail for one of
    them.

    Args:
        search: free-text search against name/description.
        parent: restrict to direct children of this StockLocation ID. Omit to
            get only top-level (root) locations by default - pass
            filters={"cascade": true} to include locations at every level
            instead, or filters={"parent": <id>, "cascade": true} to get all
            descendants of a specific location rather than just its direct
            children.
        ordering: field to sort results by, e.g. "name" ('-' prefix for
            descending, omit it for ascending). Call describe_filters("location")
            and check its ordering_fields list for valid values - an
            unrecognized field is silently ignored (no error, no sort) rather
            than rejected.
        filters: additional filter parameters beyond the named arguments
            above - call describe_filters("location") to see what's available.
        limit: maximum number of results to return - defaults to 100 (the
            maximum) to minimize round trips for large result sets; pass a
            smaller value to page through results in smaller batches.
        offset: pagination offset.
    """
    base: dict[str, Any] = {}
    if search is not None:
        base["search"] = search
    if parent is not None:
        base["parent"] = parent
    if ordering is not None:
        base["ordering"] = ordering

    params = build_query_params(base, filters, limit, offset)

    return await call_view(
        resolve_view("stock.api", "StockLocationList"),
        "GET",
        "/api/stock/location/",
        query_params=params,
    )


@mcp.tool()
async def get_location(location_id: int, filters: dict[str, Any] | None = None) -> dict:
    """Get full detail for a single stock location by its ID.

    Returns the same object shape as one entry in list_locations's
    `results` array. Get a valid ID from list_locations (its `pk` field)
    if you don't already have one.

    Args:
        location_id: the StockLocation's database ID.
        filters: optional-field toggles beyond what's returned by default -
            call describe_filters("location") and check its optional_fields.

    Raises:
        ToolError: no location exists with that ID, or the caller doesn't
            have permission to view it.
    """
    return await call_view(
        resolve_view("stock.api", "StockLocationDetail"),
        "GET",
        f"/api/stock/location/{location_id}/",
        pk=location_id,
        query_params=filters,
    )


@mcp.tool()
async def get_location_tree(limit: int = 100, offset: int = 0) -> dict:
    """Get the stock location hierarchy as a flat list with parent links and levels.

    Returns a paginated envelope whose results carry pk, name, parent and
    level, cheap to fetch in full to understand how locations nest.

    Args:
        limit: maximum number of results.
        offset: pagination offset.
    """
    return await call_view(
        resolve_view("stock.api", "StockLocationTree"),
        "GET",
        "/api/stock/location/tree/",
        query_params={"limit": clamp_limit(limit), "offset": offset},
    )


@mcp.tool()
async def create_location(
    name: str,
    parent: int | None = None,
    description: str = "",
    structural: bool | None = None,
    external: bool | None = None,
    location_type: int | None = None,
) -> dict:
    """Create a stock location.

    A write: blocked while the plugin's Read Only setting is on, and needs
    the stock location add permission.

    Args:
        name: name.
        parent: parent stock location ID; omit for a top-level one.
        description: description.
        structural: True if stock can't be placed directly, only in sublocations.
        external: True for an external location (e.g. at a supplier).
        location_type: StockLocationType ID.
    """
    data: dict[str, Any] = {"name": name, "description": description, "parent": parent}
    for key, value in (("structural", structural), ("external", external), ("location_type", location_type)):
        if value is not None:
            data[key] = value
    return await call_view(resolve_view("stock.api", "StockLocationList"), "POST", "/api/stock/location/", data=data)


@mcp.tool()
async def update_location(
    location_id: int,
    name: str | None = None,
    description: str | None = None,
    parent: int | None = None,
    move_to_top: bool = False,
    structural: bool | None = None,
    external: bool | None = None,
    location_type: int | None = None,
) -> dict:
    """Change a stock location. Only the fields you pass change.

    A write: blocked while the plugin's Read Only setting is on, and needs
    the stock location change permission.

    Args:
        location_id: the stock location ID.
        name: new name.
        description: new description.
        parent: new parent stock location ID.
        move_to_top: True to make it top-level (clears the parent).
        structural: True if stock can't be placed directly, only in sublocations.
        external: True for an external location (e.g. at a supplier).
        location_type: StockLocationType ID.
    """
    fields: dict[str, Any] = {"name": name, "description": description, "parent": parent}
    fields.update(structural=structural, external=external, location_type=location_type)
    data = {k: v for k, v in fields.items() if v is not None}
    if move_to_top:
        data["parent"] = None
    if not data:
        raise ToolError("Pass at least one field to change")
    return await call_view(
        resolve_view("stock.api", "StockLocationDetail"), "PATCH", f"/api/stock/location/{location_id}/", pk=location_id, data=data
    )


@mcp.tool()
async def delete_location(location_id: int, delete_stock_items: bool = False, delete_sub_locations: bool = False) -> dict:
    """Delete a stock location.

    A write: blocked while the plugin's Read Only setting is on, and needs
    the stock location delete permission. InvenTree's own rules decide what happens
    to what's inside; by default children and contents move up to the
    parent.

    Args:
        location_id: the stock location ID.
        delete_stock_items: also delete the stock in it (instead of moving it up).
        delete_sub_locations: also delete sublocations (instead of moving them up).
    """
    params: dict[str, Any] = {"delete_stock_items": delete_stock_items, "delete_sub_locations": delete_sub_locations}
    await call_view(
        resolve_view("stock.api", "StockLocationDetail"),
        "DELETE",
        f"/api/stock/location/{location_id}/",
        pk=location_id,
        data=params,
    )
    return {"deleted": location_id}
