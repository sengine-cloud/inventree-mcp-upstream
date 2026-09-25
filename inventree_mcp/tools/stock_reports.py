"""Stock aggregation tools: quantity by category and location.

Built only from the regular list views (via call_view), so the caller's view
permissions apply and nothing reads the ORM directly. They page through
stock, parts, categories and locations and aggregate in Python, which suits
small-to-medium inventories; beyond MAX_ROWS rows per list they refuse rather
than return a partial total.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from ..mcp_server import mcp
from ..proxy import call_view
from ..view_resolution import resolve_view

MAX_ROWS = 20_000
_PAGE = 100


async def _fetch_all(module: str, view: str, path: str, params: dict[str, Any] | None = None) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        page = await call_view(
            resolve_view(module, view),
            "GET",
            path,
            query_params={**(params or {}), "limit": _PAGE, "offset": offset},
        )
        results = page.get("results", []) if isinstance(page, dict) else page
        rows.extend(results)
        if not isinstance(page, dict) or not page.get("next") or not results:
            return rows
        offset += len(results)
        if offset >= MAX_ROWS:
            raise ToolError(f"More than {MAX_ROWS} rows in {path}; too large to aggregate here")


def _in_subtree(pathstring: str, root_path: str) -> bool:
    return pathstring == root_path or pathstring.startswith(root_path + "/")


async def _pivot(category_id: int | None, location_id: int | None, max_depth: int | None) -> list[dict]:
    categories = {
        c["pk"]: c for c in await _fetch_all("part.api", "CategoryList", "/api/part/category/")
    }
    locations = {
        loc["pk"]: loc for loc in await _fetch_all("stock.api", "StockLocationList", "/api/stock/location/")
    }
    part_category = {
        p["pk"]: p.get("category") for p in await _fetch_all("part.api", "PartList", "/api/part/")
    }
    items = await _fetch_all("stock.api", "StockList", "/api/stock/")

    def path_of(table: dict[int, dict], pk: int | None) -> str:
        return (table.get(pk) or {}).get("pathstring") or "" if pk is not None else ""

    root_cat = path_of(categories, category_id) if category_id is not None else None
    root_loc = path_of(locations, location_id) if location_id is not None else None
    root_depth = root_cat.count("/") if root_cat else 0

    totals: dict[tuple[int | None, int | None], float] = defaultdict(float)
    for item in items:
        cat = part_category.get(item.get("part"))
        loc = item.get("location")
        if root_cat is not None and not (cat is not None and _in_subtree(path_of(categories, cat), root_cat)):
            continue
        if root_loc is not None and not (loc is not None and _in_subtree(path_of(locations, loc), root_loc)):
            continue
        too_deep = root_cat is not None and max_depth is not None
        if too_deep and path_of(categories, cat).count("/") - root_depth > max_depth:
            continue
        totals[(cat, loc)] += float(item.get("quantity") or 0)

    rows = []
    for (cat, loc), qty in sorted(totals.items(), key=lambda kv: (kv[0][0] or 0, kv[0][1] or 0)):
        c = categories.get(cat) or {}
        lo = locations.get(loc) or {}
        rows.append({
            "category_id": cat,
            "category_name": c.get("name", "Uncategorized" if cat is None else "Unknown"),
            "category_path": c.get("pathstring", ""),
            "location_id": loc,
            "location_name": lo.get("name", "Unassigned" if loc is None else "Unknown"),
            "location_path": lo.get("pathstring", ""),
            "total_quantity": qty,
        })
    return rows


@mcp.tool()
async def stock_by_category_and_location(category_id: int | None = None) -> dict:
    """Total stock quantity per (part category, stock location) pair.

    A warehouse overview in one call. Stock with no location is reported
    under location "Unassigned".

    Args:
        category_id: only this category and its subcategories.

    Returns:
        {"rows": [{category_id, category_name, location_id, location_name, total_quantity}, ...]}
    """
    rows = await _pivot(category_id, None, None)
    keep = ("category_id", "category_name", "location_id", "location_name", "total_quantity")
    return {"rows": [{k: r[k] for k in keep} for r in rows]}


@mcp.tool()
async def stock_pivot(
    category_id: int | None = None,
    location_id: int | None = None,
    max_depth: int | None = None,
) -> dict:
    """Stock quantity per category and location, with full hierarchy paths.

    Args:
        category_id: only this category and its subcategories.
        location_id: only this location and its sublocations.
        max_depth: with category_id, how many category levels below it to
            include (0 = that category only).

    Returns:
        {"rows": [{category_id, category_name, category_path, location_id,
        location_name, location_path, total_quantity}, ...]}
    """
    return {"rows": await _pivot(category_id, location_id, max_depth)}
