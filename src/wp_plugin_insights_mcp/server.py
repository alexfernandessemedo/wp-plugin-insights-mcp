"""MCP server for public WordPress.org plugin directory data."""

import html
import re

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

API_URL = "https://api.wordpress.org/plugins/info/1.2/"

mcp = MCPServer("WP Plugin Insights")


def strip_html(text: str) -> str:
    """Remove HTML tags and turn codes like &amp; back into normal characters."""
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def summarise_plugin(data: dict) -> dict:
    """Keep only the useful fields from the API response."""
    return {
        "name": strip_html(data.get("name", "")),
        "slug": data.get("slug"),
        "author": strip_html(data.get("author", "")),
        "current_version": data.get("version"),
        "active_installs_at_least": data.get("active_installs"),
        "rating_out_of_5": round(data.get("rating", 0) / 20, 1),
        "number_of_ratings": data.get("num_ratings"),
        "ratings_breakdown": data.get("ratings"),
        "support_threads_recent": data.get("support_threads"),
        "support_threads_resolved_recent": data.get("support_threads_resolved"),
        "first_added": data.get("added"),
        "last_updated": data.get("last_updated"),
        "requires_wordpress": data.get("requires"),
        "tested_up_to_wordpress": data.get("tested"),
        "requires_php": data.get("requires_php"),
        "tags": list((data.get("tags") or {}).values()),
        "business_model": data.get("business_model") or None,
        "plugin_page": f"https://wordpress.org/plugins/{data.get('slug')}/",
    }


@mcp.tool()
async def get_plugin_details(slug: str) -> dict:
    """Get key facts about a plugin in the WordPress.org directory.

    Returns installs, ratings, versions, launch and update dates,
    compatibility and tags. Active installs are a rounded lower bound
    (for example 5000000 means "5 million or more").

    Args:
        slug: The plugin's short name from its WordPress.org URL,
            for example "akismet" for wordpress.org/plugins/akismet/.
    """
    params = {"action": "plugin_information", "request[slug]": slug}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(API_URL, params=params)

    if response.status_code == 404:
        raise ToolError(f"No plugin found with the slug '{slug}'.")
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict) or "error" in data:
        raise ToolError(f"No plugin found with the slug '{slug}'.")

    return summarise_plugin(data)