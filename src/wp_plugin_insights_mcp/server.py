"""MCP server for public WordPress.org plugin directory data."""

import html
import re
from datetime import date, timedelta
from statistics import median
from typing import Annotated

import httpx
from pydantic import Field
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

API_URL = "https://api.wordpress.org/plugins/info/1.2/"
DOWNLOADS_URL = "https://api.wordpress.org/stats/plugin/1.0/downloads.php"

Slug = Annotated[
    str,
    Field(
        description=(
            "The plugin's short name from its WordPress.org URL, for example "
            '"cookiebot" for wordpress.org/plugins/cookiebot/. If you only know the '
            "plugin's name, search for it first to find the slug."
        )
    ),
]

mcp = MCPServer("WP Plugin Insights")


def strip_html(text: str) -> str:
    """Remove HTML tags, turn codes like &amp; back into characters, tidy spaces."""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


async def fetch_plugin(slug: str) -> dict:
    """Fetch the full plugin_information response for one plugin."""
    params = {"action": "plugin_information", "request[slug]": slug}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(API_URL, params=params)

    if response.status_code == 404:
        raise ToolError(f"No plugin found with the slug '{slug}'.")
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict) or "error" in data:
        raise ToolError(f"No plugin found with the slug '{slug}'.")
    return data


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


def parse_reviews(reviews_html: str) -> list[dict]:
    """Turn the reviews HTML from the API into a clean list of reviews.

    Keeps the reviewer's username (for following up on the review thread)
    but not their display name, avatar or profile link.
    """
    reviews = []
    for block in reviews_html.split('<div class="review">')[1:]:
        title = re.search(r'<h4 class="review-title">(.*?)</h4>', block, re.S)
        rating = re.search(r'data-rating="(\d)"', block)
        username = re.search(
            r'profiles\.wordpress\.org/([^/"]+)/"\s+class="reviewer-name"', block
        )
        date = re.search(r'<span class="review-date">(.*?)</span>', block, re.S)
        body = block.split('<div class="review-body">', 1)

        reviews.append(
            {
                "title": strip_html(title.group(1)) if title else None,
                "stars": int(rating.group(1)) if rating else None,
                "date": strip_html(date.group(1)) if date else None,
                "reviewer_username": username.group(1) if username else None,
                "text": strip_html(body[1]) if len(body) > 1 else None,
            }
        )
    return reviews


MONTHS = {
    name: number
    for number, name in enumerate(
        [
            "january", "february", "march", "april", "may", "june", "july",
            "august", "september", "october", "november", "december",
        ],
        start=1,
    )
}
MONTH_PATTERN = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
DATE_PATTERNS = [
    # 2026-08-19
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), ("y", "m", "d")),
    # 19 August 2026, 19th Aug 2026
    (
        re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{MONTH_PATTERN}\.?,?\s+(\d{{4}})", re.I),
        ("d", "month", "y"),
    ),
    # August 19, 2026, April 6th 2026
    (
        re.compile(rf"\b{MONTH_PATTERN}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", re.I),
        ("month", "d", "y"),
    ),
]
VERSION_HEADING = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.S)
VERSION_TEXT = re.compile(r"^\s*(?:version\s*)?v?(\d+(?:\.\d+)+)\b", re.I)


def find_date(text: str) -> date | None:
    """Find the first date in a piece of text, in any of the common formats."""
    best = None
    for pattern, order in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        parts = dict(zip(order, match.groups()))
        month = parts.get("m") or MONTHS.get(next(
            (name for name in MONTHS if name.startswith(parts["month"].lower()[:3])), ""
        ))
        try:
            found = date(int(parts["y"]), int(month), int(parts["d"]))
        except (TypeError, ValueError):
            continue
        if best is None or match.start() < best[0]:
            best = (match.start(), found)
    return best[1] if best else None


def parse_releases(changelog_html: str) -> list[dict]:
    """Read version numbers and release dates from a plugin's changelog.

    Developers write changelogs in different ways, so a version only gets a
    date if one appears in its heading or just below it.
    """
    headings = [
        (m, VERSION_TEXT.match(strip_html(m.group(1))))
        for m in VERSION_HEADING.finditer(changelog_html)
    ]
    headings = [(m, v) for m, v in headings if v]

    releases = []
    for i, (heading, version) in enumerate(headings):
        end = headings[i + 1][0].start() if i + 1 < len(headings) else len(changelog_html)
        nearby = strip_html(heading.group(1) + " " + changelog_html[heading.end():end])[:300]
        released = find_date(nearby)
        releases.append(
            {"version": version.group(1), "date": released.isoformat() if released else None}
        )
    return releases


@mcp.tool()
async def get_plugin_details(slug: Slug) -> dict:
    """Get key facts about a plugin in the WordPress.org directory.

    Returns installs, ratings, versions, launch and update dates,
    compatibility and tags. Active installs are a rounded lower bound
    (for example 5000000 means "5 million or more"), and WordPress.org
    does not publish their history.
    """
    data = await fetch_plugin(slug)
    return summarise_plugin(data)


@mcp.tool()
async def get_recent_reviews(
    slug: Slug,
    include_usernames: Annotated[
        bool,
        Field(
            description=(
                "Leave as false unless the user has asked for reviewer "
                "usernames, for example to follow up on a review."
            )
        ),
    ] = False,
    review_numbers: Annotated[
        list[int] | None,
        Field(
            description=(
                "Only used when include_usernames is true. The numbers of the "
                "reviews the user wants usernames for. Leave empty for all."
            )
        ),
    ] = None,
) -> dict:
    """Get the most recent user reviews of a WordPress.org plugin.

    Returns up to the 10 latest reviews, numbered, each with a title, star
    rating, date and text. This is only the latest few reviews, not the full
    history, so avoid drawing conclusions about long-term trends from it.
    Plugin developers can reply to a review publicly from the plugin's
    reviews page.
    """
    data = await fetch_plugin(slug)
    reviews_html = (data.get("sections") or {}).get("reviews", "")
    reviews = parse_reviews(reviews_html)

    wanted = set(review_numbers or [])
    for number, review in enumerate(reviews, start=1):
        show_username = include_usernames and (not wanted or number in wanted)
        if not show_username:
            review.pop("reviewer_username", None)
        reviews[number - 1] = {"number": number, **review}

    result = {
        "plugin": strip_html(data.get("name", "")),
        "reviews_page": f"https://wordpress.org/support/plugin/{slug}/reviews/",
        "reviews": reviews,
    }
    if not include_usernames:
        result["follow_up"] = (
            "Reviewer usernames are hidden by default. After presenting the "
            "reviews, end with one short, friendly question asking whether the "
            "user would like the reviewer usernames, for all reviews or for "
            "specific ones by number, for example to reply to a review. If "
            "they say yes, call this tool again with include_usernames set to "
            "true and review_numbers set to the ones they chose."
        )
    return result


@mcp.tool()
async def get_release_history(slug: Slug) -> dict:
    """Get a plugin's release history: version numbers and release dates.

    Dates are read from the plugin's changelog, which each developer writes
    differently, so some or all versions may have no date. The changelog
    often only covers recent versions. The latest release date comes from
    WordPress.org directly and is always reliable.
    """
    data = await fetch_plugin(slug)
    releases = parse_releases((data.get("sections") or {}).get("changelog", ""))
    dated = [r for r in releases if r["date"]]
    return {
        "plugin": strip_html(data.get("name", "")),
        "current_version": data.get("version"),
        "latest_release_date": (data.get("last_updated") or "")[:10] or None,
        "versions_in_changelog": len(releases),
        "versions_with_dates": len(dated),
        "releases": releases,
    }


def release_effect(daily: dict[date, int], release_day: date) -> dict | None:
    """Compare average daily downloads in the week before and after a release."""
    before = [daily[d] for d in daily if release_day - timedelta(days=7) <= d < release_day]
    after = [daily[d] for d in daily if release_day <= d < release_day + timedelta(days=7)]
    if len(before) < 3 or len(after) < 3:
        return None
    avg_before = sum(before) / len(before)
    avg_after = sum(after) / len(after)
    return {
        "release_date": release_day.isoformat(),
        "average_daily_downloads_week_before": round(avg_before),
        "average_daily_downloads_week_after": round(avg_after),
        "change": f"{avg_after / avg_before:.1f}x" if avg_before else None,
    }


@mcp.tool()
async def get_download_history(
    slug: Slug,
    days: Annotated[
        int,
        Field(
            ge=7,
            le=730,
            description=(
                "How many recent days to include, up to 730 (about two years). "
                "Check the returned period, as some plugins have less history."
            ),
        ),
    ] = 90,
) -> dict:
    """Get daily download counts for a WordPress.org plugin.

    Downloads are not the same as installs. Every time an existing site
    updates the plugin, that counts as a download, so downloads jump after
    each new release as existing users update. Treat spikes near a release
    as mostly updates, not new users. The baseline between releases (the
    median) is a better guide to steady demand. For how many sites actually
    use the plugin, use active installs from get_plugin_details instead.
    """
    plugin = await fetch_plugin(slug)

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(DOWNLOADS_URL, params={"slug": slug, "limit": days})
    response.raise_for_status()
    raw = response.json()

    if not isinstance(raw, dict) or not raw:
        raise ToolError(f"No download history available for '{slug}'.")

    daily: dict[date, int] = {}
    for day, count in raw.items():
        try:
            daily[date.fromisoformat(day)] = int(count)
        except (TypeError, ValueError):
            continue
    if not daily:
        raise ToolError(f"Download history for '{slug}' was in an unexpected format.")

    counts = list(daily.values())
    baseline = median(counts)
    first_day, last_day = min(daily), max(daily)

    # Release dates: the changelog where it has them, plus the latest release,
    # which WordPress.org always records.
    release_dates: dict[date, str] = {}
    for release in parse_releases((plugin.get("sections") or {}).get("changelog", "")):
        if release["date"]:
            release_dates.setdefault(date.fromisoformat(release["date"]), release["version"])
    if plugin.get("version") not in release_dates.values():
        try:
            latest = date.fromisoformat((plugin.get("last_updated") or "")[:10])
            release_dates.setdefault(latest, plugin.get("version"))
        except ValueError:
            pass
    releases_in_period = {
        d: v for d, v in sorted(release_dates.items()) if first_day <= d <= last_day
    }

    def nearby_release(day: date) -> str | None:
        """The release made on this day or up to 3 days before, if any."""
        for d, version in reversed(releases_in_period.items()):
            if timedelta(0) <= day - d <= timedelta(days=3):
                return version
        return None

    spikes = sorted(
        (d for d, c in daily.items() if baseline and c > 2 * baseline),
        key=lambda d: daily[d],
        reverse=True,
    )[:15]
    spike_days = [
        {"date": d.isoformat(), "downloads": daily[d], "likely_release": nearby_release(d)}
        for d in sorted(spikes)
    ]

    release_effects = []
    for d, version in list(releases_in_period.items())[-10:]:
        effect = release_effect(daily, d)
        if effect:
            release_effects.append({"version": version, **effect})

    # Long periods are summarised by week to keep the response a sensible size.
    if len(daily) > 120:
        weekly: dict[str, int] = {}
        for d, c in sorted(daily.items()):
            week_start = (d - timedelta(days=d.weekday())).isoformat()
            weekly[week_start] = weekly.get(week_start, 0) + c
        series = {"weekly_downloads_by_week_starting": weekly}
    else:
        series = {"daily_downloads": {d.isoformat(): c for d, c in sorted(daily.items())}}

    return {
        "plugin": strip_html(plugin.get("name", "")),
        "period": f"{first_day.isoformat()} to {last_day.isoformat()}",
        "total_downloads": sum(counts),
        "median_daily_downloads": round(baseline),
        "releases_in_period": [
            {"version": v, "date": d.isoformat()} for d, v in releases_in_period.items()
        ],
        "spike_days": spike_days,
        "release_effects": release_effects,
        **series,
        "note": (
            "Downloads include updates by existing users, so spikes usually "
            "follow new releases. A spike with a likely_release is probably "
            "existing sites updating, not new users. A spike without one may "
            "be a release missing from the changelog, or something else "
            "worth investigating."
        ),
    }