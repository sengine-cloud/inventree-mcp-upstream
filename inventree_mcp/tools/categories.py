"""MCP tools for querying InvenTree PartCategory data."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from ..mcp_server import mcp
from ..proxy import call_view
from ..view_resolution import resolve_view
from ._common import build_query_params, clamp_limit


@mcp.tool()
async def list_categories(
    search: str | None = None,
    parent: int | None = None,
    ordering: str | None = None,
    filters: dict[str, Any] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List part categories.

    Returns a paginated envelope: {count, next, previous, results}. Each
    entry in `results` has the same shape as get_category's return value -
    use its `pk` field with get_category to fetch full detail for one of
    them.

    Args:
        search: free-text search against name/description.
        parent: restrict to direct children of this PartCategory ID. Omit to
            get only top-level (root) categories by default - pass
            filters={"cascade": true} to include categories at every level
            instead, or filters={"parent": <id>, "cascade": true} to get all
            descendants of a specific category rather than just its direct
            children.
        ordering: field to sort results by, e.g. "name" ('-' prefix for
            descending, omit it for ascending). Call describe_filters("category")
            and check its ordering_fields list for valid values - an
            unrecognized field is silently ignored (no error, no sort) rather
            than rejected.
        filters: additional filter parameters beyond the named arguments
            above - call describe_filters("category") to see what's available.
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
        resolve_view("part.api", "CategoryList"),
        "GET",
        "/api/part/category/",
        query_params=params,
    )


@mcp.tool()
async def get_category(category_id: int, filters: dict[str, Any] | None = None) -> dict:
    """Get full detail for a single part category by its ID.

    Returns the same object shape as one entry in list_categories's
    `results` array. Get a valid ID from list_categories (its `pk` field)
    if you don't already have one.

    Args:
        category_id: the PartCategory's database ID.
        filters: optional-field toggles beyond what's returned by default -
            call describe_filters("category") and check its optional_fields.

    Raises:
        ToolError: no category exists with that ID, or the caller doesn't
            have permission to view it.
    """
    return await call_view(
        resolve_view("part.api", "CategoryDetail"),
        "GET",
        f"/api/part/category/{category_id}/",
        pk=category_id,
        query_params=filters,
    )


@mcp.tool()
async def get_category_tree(limit: int = 100, offset: int = 0) -> dict:
    """Get the part category hierarchy as a flat list with parent links and levels.

    Returns a paginated envelope whose results carry pk, name, parent and
    level, cheap to fetch in full to understand how categories nest.

    Args:
        limit: maximum number of results.
        offset: pagination offset.
    """
    return await call_view(
        resolve_view("part.api", "CategoryTree"),
        "GET",
        "/api/part/category/tree/",
        query_params={"limit": clamp_limit(limit), "offset": offset},
    )


@mcp.tool()
async def create_category(
    name: str,
    parent: int | None = None,
    description: str = "",
    structural: bool | None = None,
    default_location: int | None = None,
    default_keywords: str | None = None,
) -> dict:
    """Create a part category.

    A write: blocked while the plugin's Read Only setting is on, and needs
    the part category add permission.

    Args:
        name: name.
        parent: parent part category ID; omit for a top-level one.
        description: description.
        structural: True if parts can't be assigned directly, only to subcategories.
        default_location: default StockLocation ID for parts in it.
        default_keywords: default keywords for new parts in it.
    """
    data: dict[str, Any] = {"name": name, "description": description, "parent": parent}
    for key, value in (("structural", structural), ("default_location", default_location), ("default_keywords", default_keywords)):
        if value is not None:
            data[key] = value
    return await call_view(resolve_view("part.api", "CategoryList"), "POST", "/api/part/category/", data=data)


@mcp.tool()
async def update_category(
    category_id: int,
    name: str | None = None,
    description: str | None = None,
    parent: int | None = None,
    move_to_top: bool = False,
    structural: bool | None = None,
    default_location: int | None = None,
    default_keywords: str | None = None,
) -> dict:
    """Change a part category. Only the fields you pass change.

    A write: blocked while the plugin's Read Only setting is on, and needs
    the part category change permission.

    Args:
        category_id: the part category ID.
        name: new name.
        description: new description.
        parent: new parent part category ID.
        move_to_top: True to make it top-level (clears the parent).
        structural: True if parts can't be assigned directly, only to subcategories.
        default_location: default StockLocation ID for parts in it.
        default_keywords: default keywords for new parts in it.
    """
    fields: dict[str, Any] = {"name": name, "description": description, "parent": parent}
    fields.update(structural=structural, default_location=default_location, default_keywords=default_keywords)
    data = {k: v for k, v in fields.items() if v is not None}
    if move_to_top:
        data["parent"] = None
    if not data:
        raise ToolError("Pass at least one field to change")
    return await call_view(
        resolve_view("part.api", "CategoryDetail"), "PATCH", f"/api/part/category/{category_id}/", pk=category_id, data=data
    )


@mcp.tool()
async def delete_category(category_id: int, delete_parts: bool = False, delete_child_categories: bool = False) -> dict:
    """Delete a part category.

    A write: blocked while the plugin's Read Only setting is on, and needs
    the part category delete permission. InvenTree's own rules decide what happens
    to what's inside; by default children and contents move up to the
    parent.

    Args:
        category_id: the part category ID.
        delete_parts: also delete the parts in it (instead of moving them up).
        delete_child_categories: also delete subcategories (instead of moving them up).
    """
    params: dict[str, Any] = {"delete_parts": delete_parts, "delete_child_categories": delete_child_categories}
    await call_view(
        resolve_view("part.api", "CategoryDetail"),
        "DELETE",
        f"/api/part/category/{category_id}/",
        pk=category_id,
        data=params,
    )
    return {"deleted": category_id}
