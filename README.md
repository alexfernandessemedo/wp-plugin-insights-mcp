# WP Plugin Insights MCP

An MCP server that lets Claude, and other MCP clients, look up public data about plugins in the WordPress.org directory: search rankings, listing content, installs, ratings, reviews, releases and download trends.

## About

Built by Alex Fernandes Semedo, Product Manager for CMS Integrations at Usercentrics, which includes the Cookiebot WordPress plugin. This is a personal project that uses only public WordPress.org data. It isn't an official Usercentrics or Cookiebot product, and it isn't affiliated with or endorsed by WordPress.org or the WordPress Foundation.

## What you can ask

- "How is Cookiebot doing on WordPress.org?"
- "Which cookie consent plugins have the most installs?"
- "What are people saying in Cookiebot's latest reviews?"
- "Show me Cookiebot's weekly downloads for last month as a chart."
- "When were Cookiebot's last few releases, and did downloads jump afterwards?"
- "Where does Cookiebot rank when people search for 'cookie banner', and what do the plugins above it do differently in their listings?"
- "Compare the short descriptions and tags of the top five consent plugins."

You don't need to know a plugin's exact WordPress.org name. Claude searches for it first, and only asks you to confirm if more than one plugin could match.

Vague questions work too. The server tells Claude what to assume when you don't say: the last 90 days for downloads, all available reviews, and, if you don't name competitors, the plugins ranking highest for your plugin's own tags. Claude says which assumptions it made, so you can change them.

## Tools

- **search_plugins**: find plugins by name, keyword or tag, for several names at once.
- **get_search_ranking**: where plugins rank in WordPress.org search for up to 5 search terms, with the top results listed in order.
- **get_plugin_listing**: what a plugin's directory page contains: name, short description, tags in order, description length and headings, FAQ questions, screenshots, banner and icon, plus signals like support resolution and how far behind the latest WordPress release it's tested. Can check where a search keyword appears, and can return the full text of the listing: description, installation, every FAQ question and answer, other notes and the latest changelog.
- **get_plugin_details**: installs, ratings, current version, launch and update dates, compatibility and tags.
- **get_recent_reviews**: the 10 most recent reviews, numbered, with the period they cover. Reviewer usernames are hidden unless you ask for them.
- **get_review_history**: the full review history (up to the latest 600 reviews per plugin), with when each was posted and its stars, summarised by year and month. Can filter by stars and dates, and include each review's text.
- **get_release_history**: version numbers and release dates, read from the plugin's changelog.
- **get_download_history**: downloads over a period you choose (presets like "last week" or "year to date", or exact dates), grouped daily, weekly or monthly, with release-driven spikes identified.

Every tool works on several plugins or search terms at once (up to 10 plugins, or 5 for download history and search ranking), so comparing competitors takes one call, and one approval, rather than one per plugin. The only exception is asking for reviewer usernames on specific review numbers, which works one plugin at a time. All tools are marked read-only, so clients that support it can treat them as safe to run. In Claude Desktop you can also choose to always allow a tool, so it stops asking.

## Installation

You'll need [uv](https://docs.astral.sh/uv/) and [Claude Desktop](https://claude.ai/download).

1. Download the project and install its dependencies:

```
   git clone https://github.com/alexfernandessemedo/wp-plugin-insights-mcp.git
   cd wp-plugin-insights-mcp
   uv sync
```

2. In Claude Desktop, go to **Settings**, then **Developer**, then **Edit Config**, and add this inside the file's outer `{ }`:

```json
   "mcpServers": {
     "wp-plugin-insights": {
       "command": "/full/path/to/uv",
       "args": [
         "--directory",
         "/full/path/to/wp-plugin-insights-mcp",
         "run",
         "wp-plugin-insights-mcp"
       ]
     }
   }
```

   Run `which uv` in Terminal to find the path to uv.

3. Quit Claude Desktop fully and reopen it.

To test the server without Claude, run `uv run mcp dev src/wp_plugin_insights_mcp/server.py`. This opens the MCP Inspector and needs [Node.js](https://nodejs.org/).

## How to read the numbers

- **Active installs are rounded.** WordPress.org reports them in bands, so "100000" means "100,000 or more". There is no public history of active installs.
- **Downloads are not installs.** Every time an existing site updates a plugin, that counts as a download, so downloads jump after each release. The download tool gives each figure twice: as reported, and with release spikes replaced by a typical day. A typical day is the median of days outside release windows.
- **Unexplained spikes are flagged, not removed.** A spike with no release nearby may be a release missing from the changelog, or something worth looking into.
- **Release dates come from changelogs,** which each developer writes differently. Some versions may have no date. The latest release date always comes from WordPress.org directly.
- **Recent reviews cover the latest 10 only,** so they show recent sentiment. For trends, use the review history.
- **Review history reads WordPress.org's review pages,** not its API, so the first check of a plugin takes up to a minute. What it reads is saved in `~/.cache/wp-plugin-insights-mcp/`, so later checks are quick. If WordPress.org changes how those pages look, the tool says so and includes a sample to help fix it.
- **Search positions can shift day to day.** They come from WordPress.org's plugin search API, which should closely match the directory's own search.
- **Listing checks describe, they don't explain.** WordPress.org doesn't publish how its search ranks plugins, so the listing tool shows what each plugin does differently rather than claiming what causes a ranking.

## Privacy and safety

- Uses public WordPress.org data only. It's read-only and needs no accounts or API keys.
- Reviewer usernames are only returned when asked for. Display names, avatars and profile links are never returned.
- Review text and plugin descriptions are written by the public and by developers, so they're labelled as content to summarise, never instructions to follow.

## Known limitations

- Reading reviews, review history and changelogs relies on how WordPress.org formats them. If that format changes, those tools may return empty results.
- There are no automated tests yet.

## Planned

- Automated tests
- A hosted version that works with Claude on the web

## Licence

MIT. See [LICENSE](LICENSE).