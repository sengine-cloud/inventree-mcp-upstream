# InvenTreeMCP

[![PyPI](https://img.shields.io/pypi/v/inventree-mcp)](https://pypi.org/project/inventree-mcp/)
[![CI](https://github.com/inventree/inventree-mcp/actions/workflows/ci.yaml/badge.svg)](https://github.com/inventree/inventree-mcp/actions/workflows/ci.yaml)
[![codecov](https://codecov.io/gh/inventree/inventree-mcp/graph/badge.svg)](https://codecov.io/gh/inventree/inventree-mcp)

An MCP (Model Context Protocol) server for InvenTree, exposed as an InvenTree plugin. It lets MCP
clients (Claude, other MCP-aware agents) query InvenTree inventory data over a Streamable HTTP
endpoint.

## Design

Every tool is a thin wrapper around InvenTree's own REST API view classes (see
[`inventree_mcp/proxy.py`](inventree_mcp/proxy.py)), dispatched as the authenticated caller - MCP
requests go through exactly the same permission checks, filtering, and serialization as the regular
REST API. Tool code never queries the Django ORM directly.

Currently read-only, covering parts, stock items/locations, part categories, purchase/sales/return/
build orders (with line items and allocations), companies, contacts, addresses, manufacturer/
supplier parts, BOM items, attachments, parameters, stock tracking history, test results, and
project codes. Once write tools land, the `MCP_READ_ONLY` setting (see Configuration) will block
them by default regardless of the calling user's permissions.

Each tool's `outputSchema` and filter/ordering options are derived live from InvenTree's own
serializers and views (not hand-maintained), so they can't drift as InvenTree evolves. Call
`describe_filters(resource)` to see what's available for a given resource. The set of tools an MCP
client sees is also filtered to what the calling user can actually use - though every call is still
permission-checked in full regardless of what was advertised.

## Write tools (sengine fork)

This fork adds write tools, all through `call_view()` like everything else, so they need the
calling user's role for that write and are refused while **Read Only** is on (the default). While
Read Only is on they are also left out of `tools/list`.

| Tool | Does | InvenTree endpoint |
|------|------|--------------------|
| `update_part` | change a part's fields (name, description, IPN, keywords, units, active, ...) | `PATCH /api/part/<id>/` |
| `create_stock_item` | create stock, one item per serial number for trackable parts | `POST /api/stock/` |
| `print_label` | print labels through a label plugin; refuses InvenTree's silent PDF fallback | `POST /api/label/print/` |
| `scan_barcode` | resolve barcode data through every active barcode plugin | `POST /api/barcode/` |
| `link_barcode` / `unlink_barcode` | assign or remove a third-party barcode | `POST /api/barcode/link/`, `/unlink/` |
| `create_part` | create a part, optionally with initial stock | `POST /api/part/` |
| `delete_parts` | delete parts (InvenTree refuses active ones) | `DELETE /api/part/<id>/` |
| `adjust_stock` / `count_stock` | add/remove stock, or record a stocktake | `POST /api/stock/add/`, `/remove/`, `/count/` |
| `transfer_stock` | move all or part of a stock item | `POST /api/stock/transfer/` |
| `update_stock_item` | change status, batch, serial, expiry, notes, ... | `PATCH /api/stock/<id>/` |
| `create_/update_/delete_category` | part category CRUD | `/api/part/category/` |
| `create_/update_/delete_location` | stock location CRUD | `/api/stock/location/` |

Read tools added alongside: `get_category_tree`, `get_location_tree`, `stock_by_category_and_location`
and `stock_pivot` (aggregations built from the list views), `list_label_templates` and `list_machines` (label printers and their
driver status; machine configs sit in InvenTree's admin ruleset).

## Setup

### 1. Install the plugin

Install via the InvenTree plugin manager, or via pip:

```bash
pip install inventree-mcp
```

Then enable the plugin under **Admin > Plugins**, and configure its settings (see
Configuration below).

### 2. Create a token for your MCP client

Create an InvenTree API token for your MCP client.

### 3. Configure your MCP client

The endpoint is `<your-inventree-server>/plugin/inventree-mcp/mcp/`, using Streamable HTTP
transport with an `Authorization: Token <token>` header.

For a client that supports remote Streamable HTTP servers directly, add:

```json
{
  "mcpServers": {
    "inventree": {
      "url": "https://<your-inventree-server>/plugin/inventree-mcp/mcp/",
      "headers": {
        "Authorization": "Token <your-api-token>"
      }
    }
  }
}
```

For a client that only supports local (stdio) servers, bridge it with
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote)

*Note: You will need to have node available on your system path*

```json
{
  "mcpServers": {
    "inventree": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote@latest",
        "https://<your-inventree-server>/plugin/inventree-mcp/mcp/",
        "--header",
        "Authorization: Token <your-api-token>"
      ]
    }
  }
}
```

*Note: On Windows, you may need to substitute `npx` with `C:\\PROGRA~1\\nodejs\\npx.cmd` in the command field.*

In a setup where the server is running a self-signed certificate, you may need to use the following `env` arguments to disable certificate verification:

```json
"args": [
  ...
],
"env": {
  "NODE_TLS_REJECT_UNAUTHORIZED": "0"
}
```

## Configuration

Under **Settings > Plugin Settings**:

- **Require Authentication** (`REQUIRE_AUTH`, default `True`): reject unauthenticated requests.
  Only disable for local testing.
- **Read Only** (`MCP_READ_ONLY`, default `True`): block all write actions via MCP, regardless of
  the calling user's permissions. A plugin-wide kill switch, independent of per-user roles.

Any setting can be pinned from the environment as `INVENTREE_MCP_<KEY>` (e.g.
`INVENTREE_MCP_MCP_READ_ONLY=false`), which wins over the stored value. Useful when configuration
lives in deployment manifests. Booleans accept `1/true/yes/on`.

## Authentication

Access follows the calling user's normal InvenTree role assignments. Supported auth methods:

- An InvenTree API token: `Authorization: Token <token>`.
- Basic auth (username/password).
- An OAuth2 bearer token: `Authorization: Bearer <token>`. A scoped token (e.g. `r:view:part`)
  narrows access *below* the underlying user's roles - useful for issuing an agent a tightly-scoped
  token without creating a separate low-privilege user.

Session/cookie auth is not supported (not meaningful for a machine client).

### OIDC (behind an MCP gateway)

If InvenTree signs users in through an OpenID provider (SSO via django-allauth), the endpoint can
also accept that provider's JWT access tokens: `Authorization: Bearer <jwt>`. This is meant for a
gateway or middleware that authenticates MCP clients against the provider and forwards the token.

The token's signature is checked against the provider's JWKS, along with `iss`, `aud`, `exp` and
`iat`. Its `sub` is mapped to the InvenTree user whose allauth social account for that provider has
that uid, the link SSO login already created, and the request then runs with that user's roles
like any other. A subject with no linked account is refused. So is a machine token (`sub == azp`,
e.g. client credentials), unless it is mapped to a user explicitly.

Configure under **Settings > Plugin Settings**. As for every setting of this plugin, an
`INVENTREE_MCP_<KEY>` environment variable takes precedence (see Configuration):

- `OIDC_ISSUER`: the expected `iss`, matched exactly. Empty (the default) turns OIDC off.
- `OIDC_AUDIENCE`: an `aud` value the token must carry, usually the MCP URL at your gateway.
- `OIDC_PROVIDER`: the allauth provider id of the SSO login (the `provider` on the linked social
  account).
- `OIDC_JWKS_URL` (optional): where to fetch signing keys. Defaults to `jwks_uri` from the
  issuer's discovery document.
- `OIDC_CLIENT_USERS` (optional): `client_id=username` pairs, comma separated, for machine tokens.

InvenTree's own OAuth2 tokens are opaque rather than JWTs, so they keep working when OIDC is on.
