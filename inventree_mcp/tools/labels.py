"""MCP tools for label templates, machines and label printing."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from ..mcp_server import mcp
from ..proxy import call_view
from ..view_resolution import resolve_view
from ._common import build_query_params


@mcp.tool()
async def list_label_templates(
    model_type: str | None = None,
    enabled: bool | None = True,
    filters: dict[str, Any] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List label templates, e.g. to find a template_id for print_label.

    Returns a paginated envelope: {count, next, previous, results}.

    Args:
        model_type: only templates for this model, e.g. "part", "stockitem"
            or "stocklocation".
        enabled: True (default) for enabled templates only, False for
            disabled ones, None for all.
        filters: additional filter parameters for the template list.
        limit: maximum number of results.
        offset: pagination offset.
    """
    base: dict[str, Any] = {}
    if model_type is not None:
        base["model_type"] = model_type
    if enabled is not None:
        base["enabled"] = enabled
    return await call_view(
        resolve_view("report.api", "LabelTemplateList"),
        "GET",
        "/api/label/template/",
        query_params=build_query_params(base, filters, limit, offset),
    )


@mcp.tool()
async def list_machines(
    machine_type: str | None = None,
    active: bool | None = None,
    filters: dict[str, Any] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List configured machines (e.g. label printers), with their live status.

    Use a label printer's `pk` as options={"machine": pk} in print_label.
    `status_text` carries driver-reported state (firmware, battery, media,
    last seen) where the driver provides it.

    Args:
        machine_type: only this machine type, e.g. "label-printer".
        active: only active (True) or inactive (False) machines.
        filters: additional filter parameters for the machine list.
        limit: maximum number of results.
        offset: pagination offset.
    """
    base: dict[str, Any] = {}
    if machine_type is not None:
        base["machine_type"] = machine_type
    if active is not None:
        base["active"] = active
    return await call_view(
        resolve_view("machine.api", "MachineList"),
        "GET",
        "/api/machine/",
        query_params=build_query_params(base, filters, limit, offset),
    )


@mcp.tool()
async def print_label(
    template_id: int,
    items: list[int],
    plugin: str,
    options: dict[str, Any] | None = None,
) -> dict:
    """Print labels for objects with a label template, through a label plugin.

    A write: blocked while the plugin's Read Only setting is on.

    The result is the print job (a data output record), not proof a label
    came out: a plugin that hands off to a machine completes later, in the
    background.

    Args:
        template_id: label template ID (see list_label_templates). Its
            model_type must match the objects in `items`.
        items: IDs of the objects to label (parts, stock items, ...).
        plugin: label printing plugin slug, e.g. "inventreelabel" (PDF) or
            "inventreelabelmachine" (a printer machine). Required on purpose:
            InvenTree otherwise falls back to the PDF plugin and ignores
            printer options.
        options: plugin-specific options, e.g. {"machine": "<machine pk>"}
            for inventreelabelmachine (see list_machines).

    Raises:
        ToolError: InvenTree printed with a different plugin than requested
            (it falls back to PDF for an unknown or inactive plugin, while
            still answering success), or the print request was rejected.
    """
    data = {**(options or {}), "template": template_id, "items": items, "plugin": plugin}
    output = await call_view(
        resolve_view("report.api", "LabelPrint"), "POST", "/api/label/print/", data=data
    )
    used = output.get("plugin") if isinstance(output, dict) else None
    if used and used != plugin:
        raise ToolError(
            f"InvenTree printed with plugin {used!r}, not {plugin!r}: {plugin!r} is not an "
            f"active label printing plugin. Output {output.get('pk')} was still created."
        )
    return output
