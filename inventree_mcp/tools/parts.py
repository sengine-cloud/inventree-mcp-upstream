"""MCP tools for querying InvenTree Part data.

Every tool here is a thin wrapper around the real part API views
(part.api.PartList / PartDetail) via proxy.call_view(), so permissions,
filtering, and serialization always match the regular REST API exactly.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from ..mcp_server import mcp
from ..proxy import call_view
from ..view_resolution import resolve_view
from ._common import build_query_params


@mcp.tool()
async def list_parts(
    search: str | None = None,
    category: int | None = None,
    active: bool | None = None,
    ordering: str | None = None,
    filters: dict[str, Any] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List parts in the InvenTree database.

    Returns a paginated envelope: {count, next, previous, results}. Each
    entry in `results` has the same shape as get_part's return value - use
    its `pk` field with get_part to fetch full detail for one of them.

    Args:
        search: free-text search against name, description, IPN, and keywords.
        category: restrict to parts in this PartCategory ID (includes sub-categories).
        active: True for only active (non-discontinued) parts, False for only
            inactive ones, omit to include both.
        ordering: field to sort results by, e.g. "-in_stock" for highest stock
            first ('-' prefix for descending, omit it for ascending). Combine
            with limit to get a "top N by X" result, e.g. ordering="-in_stock",
            limit=5 for the 5 parts with the most stock. Call
            describe_filters("part") and check its ordering_fields list for
            valid values - an unrecognized field is silently ignored (no
            error, no sort) rather than rejected.
        filters: additional filter parameters beyond the named arguments
            above - call describe_filters("part") to see what's available,
            e.g. filters={"is_variant": true}.
        limit: maximum number of results to return - defaults to 100 (the
            maximum) to minimize round trips for large result sets; pass a
            smaller value to page through results in smaller batches.
        offset: pagination offset.
    """
    base: dict[str, Any] = {}
    if search is not None:
        base["search"] = search
    if category is not None:
        base["category"] = category
    if active is not None:
        base["active"] = active
    if ordering is not None:
        base["ordering"] = ordering

    params = build_query_params(base, filters, limit, offset)

    return await call_view(
        resolve_view("part.api", "PartList"), "GET", "/api/part/", query_params=params
    )


@mcp.tool()
async def get_part(part_id: int, filters: dict[str, Any] | None = None) -> dict:
    """Get full detail for a single part by its ID.

    Returns the same object shape as one entry in list_parts's `results`
    array. Get a valid ID from list_parts (its `pk` field) if you don't
    already have one.

    Args:
        part_id: the Part's database ID.
        filters: optional-field toggles beyond what's returned by default -
            call describe_filters("part") and check its optional_fields, e.g.
            filters={"category_detail": true}.

    Raises:
        ToolError: no part exists with that ID, or the caller doesn't have
            permission to view it.
    """
    return await call_view(
        resolve_view("part.api", "PartDetail"),
        "GET",
        f"/api/part/{part_id}/",
        pk=part_id,
        query_params=filters,
    )


@mcp.tool()
async def update_part(
    part_id: int,
    name: str | None = None,
    description: str | None = None,
    IPN: str | None = None,
    revision: str | None = None,
    keywords: str | None = None,
    units: str | None = None,
    link: str | None = None,
    notes: str | None = None,
    active: bool | None = None,
    minimum_stock: float | None = None,
    default_location: int | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Update fields of an existing part. Only the fields you pass change.

    A write: blocked while the plugin's Read Only setting is on, and needs
    the part change permission.

    Args:
        part_id: the Part's database ID.
        name: new part name.
        description: new description.
        IPN: new internal part number.
        revision: new revision string.
        keywords: new search keywords.
        units: new units of measure.
        link: new external link (URL).
        notes: new notes (markdown).
        active: whether the part is active.
        minimum_stock: minimum stock level.
        default_location: default StockLocation ID for this part's stock.
        tags: the part's complete tag list (replaces the existing tags; [] clears).

    Returns:
        The updated part, same shape as get_part.
    """
    fields = {
        "name": name,
        "description": description,
        "IPN": IPN,
        "revision": revision,
        "keywords": keywords,
        "units": units,
        "link": link,
        "notes": notes,
        "active": active,
        "minimum_stock": minimum_stock,
        "default_location": default_location,
        "tags": tags,
    }
    data = {k: v for k, v in fields.items() if v is not None}
    if not data:
        raise ToolError("Pass at least one field to change")
    return await call_view(
        resolve_view("part.api", "PartDetail"),
        "PATCH",
        f"/api/part/{part_id}/",
        pk=part_id,
        data=data,
    )


@mcp.tool()
async def create_part(
    name: str,
    category: int,
    description: str = "",
    IPN: str | None = None,
    revision: str | None = None,
    keywords: str | None = None,
    units: str | None = None,
    link: str | None = None,
    notes: str | None = None,
    default_location: int | None = None,
    minimum_stock: float | None = None,
    tags: list[str] | None = None,
    component: bool | None = None,
    assembly: bool | None = None,
    purchaseable: bool | None = None,
    salable: bool | None = None,
    trackable: bool | None = None,
    virtual: bool | None = None,
    active: bool | None = None,
    initial_stock_quantity: float | None = None,
    initial_stock_location: int | None = None,
) -> dict:
    """Create a part, optionally with its first stock.

    A write: blocked while the plugin's Read Only setting is on, and needs
    the part add permission (plus stock add for initial stock).

    Args:
        name: part name.
        category: PartCategory ID.
        description: description.
        IPN: internal part number.
        revision: revision string.
        keywords: search keywords.
        units: units of measure.
        link: external link (URL).
        notes: notes (markdown).
        default_location: default StockLocation ID for its stock.
        minimum_stock: minimum stock level.
        tags: tags to set.
        component, assembly, purchaseable, salable, trackable, virtual, active:
            part flags; omitted flags take InvenTree's defaults.
        initial_stock_quantity: create this much stock right away.
        initial_stock_location: StockLocation for that initial stock.

    Returns:
        The created part, same shape as get_part.
    """
    fields = {
        "IPN": IPN,
        "revision": revision,
        "keywords": keywords,
        "units": units,
        "link": link,
        "notes": notes,
        "default_location": default_location,
        "minimum_stock": minimum_stock,
        "tags": tags,
        "component": component,
        "assembly": assembly,
        "purchaseable": purchaseable,
        "salable": salable,
        "trackable": trackable,
        "virtual": virtual,
        "active": active,
    }
    data: dict[str, Any] = {"name": name, "category": category, "description": description}
    data.update({k: v for k, v in fields.items() if v is not None})
    if initial_stock_quantity is not None:
        data["initial_stock"] = {"quantity": initial_stock_quantity, "location": initial_stock_location}
    return await call_view(resolve_view("part.api", "PartList"), "POST", "/api/part/", data=data)


@mcp.tool()
async def delete_parts(part_ids: list[int]) -> dict:
    """Delete parts by ID.

    A write: blocked while the plugin's Read Only setting is on, and needs
    the part delete permission. InvenTree refuses to delete an active part,
    so deactivate it first (update_part active=False). Each part is deleted
    separately; the result lists what was deleted and what was refused.

    Args:
        part_ids: IDs of the parts to delete.
    """
    view = resolve_view("part.api", "PartDetail")
    deleted: list[int] = []
    failed: dict[str, str] = {}
    for pk in part_ids:
        try:
            await call_view(view, "DELETE", f"/api/part/{pk}/", pk=pk)
            deleted.append(pk)
        except ToolError as exc:
            failed[str(pk)] = str(exc)
    return {"deleted": deleted, "failed": failed}
