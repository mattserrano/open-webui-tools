"""
title: last.fm
description: Discover music and fetch last.fm play history data.
author: mattserrano
version: 0.2.0
"""

import html as html_lib
import re
import requests
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Annotated, Any, Optional, Union

# --------------------------------------------------------------------------- #
# Rich UI assets (shared by every embed)
# --------------------------------------------------------------------------- #

# The embed runs in a sandboxed iframe that cannot see Open WebUI's theme, so the
# card paints its own opaque background and follows the OS light/dark preference.
_RICH_CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--muted:#6b7280;--border:#e5e7eb;--accent:#d51007;--chip:#f3f4f6;}
@media (prefers-color-scheme:dark){
:root{--bg:#171717;--fg:#f3f4f6;--muted:#9ca3af;--border:#2e2e2e;--accent:#ff5a4f;--chip:#262626;}}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-size:14px;
line-height:1.45;padding:4px;background:transparent}
.card{background:var(--bg);color:var(--fg);border:1px solid var(--border);
border-radius:14px;padding:16px;overflow:hidden}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
h1{font-size:1.1em;font-weight:700}
.head{margin-bottom:12px}.head p{color:var(--muted);font-size:.9em}
ol{list-style:none}
.row{display:flex;align-items:center;gap:10px;padding:8px 0;border-top:1px solid var(--border)}
.row:first-child{border-top:none}
.rank{width:22px;text-align:right;color:var(--muted);font-variant-numeric:tabular-nums;flex:none}
.thumb{width:44px;height:44px;border-radius:6px;object-fit:cover;flex:none;background:var(--chip)}
.main{flex:1;min-width:0}
.title{font-weight:600;overflow-wrap:anywhere}
.sub{color:var(--muted);font-size:.9em;overflow-wrap:anywhere}
.meta{margin-top:2px}
.chip{display:inline-block;background:var(--chip);color:var(--muted);border-radius:999px;
padding:1px 8px;font-size:.78em;margin:2px 4px 0 0}
.badge{display:inline-block;background:var(--accent);color:#fff;border-radius:999px;
padding:1px 8px;font-size:.72em;font-weight:600;margin-left:6px;vertical-align:middle}
.bar{height:4px;background:var(--chip);border-radius:2px;margin-top:5px;overflow:hidden}
.bar span{display:block;height:100%;background:var(--accent)}
.ask{flex:none;background:transparent;color:var(--accent);border:1px solid var(--border);
border-radius:8px;padding:3px 10px;font-size:.8em;cursor:pointer}
.ask:hover{border-color:var(--accent)}
.foot{margin-top:10px;color:var(--muted);font-size:.85em}
.hero{display:flex;gap:14px;align-items:flex-start}
.hero img{width:96px;height:96px;border-radius:10px;object-fit:cover;flex:none;background:var(--chip)}
.hero h1{font-size:1.25em}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 4px}
.stat{background:var(--chip);border-radius:10px;padding:8px 12px;min-width:90px}
.stat b{display:block;font-size:1.1em}.stat span{color:var(--muted);font-size:.78em}
.tags{margin-top:8px}
.summary{margin-top:12px;color:var(--fg);opacity:.9}
"""

# Reports height to the parent (needed when allowSameOrigin is off), wires up the
# optional "Ask" buttons (input:prompt only fills the chat box, never submits),
# and hides thumbnails that fail to load.
_RICH_SCRIPT = """
(function(){
  function h(){parent.postMessage({type:'iframe:height',height:document.documentElement.scrollHeight},'*');}
  window.addEventListener('load',h);
  if(window.ResizeObserver){new ResizeObserver(h).observe(document.body);}
  document.addEventListener('click',function(e){
    var b=e.target.closest('[data-prompt]');
    if(b){parent.postMessage({type:'input:prompt',text:b.getAttribute('data-prompt')},'*');}
  });
  document.querySelectorAll('img').forEach(function(i){
    i.addEventListener('error',function(){i.style.display='none';});
  });
})();
"""

_LASTFM_PLACEHOLDER_HASH = "2a96cbd8b46e442fc41c2b86b821562f"  # grey "star" image


class Tools:
    class UserValves(BaseModel):
        last_fm_api_key: str = Field(
            default="",
            description="Your last.fm API key",
            json_schema_extra={"input": {"type": "password"}},
        )
        last_fm_api_user: str = Field(
            default="",
            description="Your last.fm username",
        )
        enable_rich_responses: bool = Field(
            default=True,
            description="Render results as rich embedded UI cards in the chat instead of plain Markdown.",
        )

    def _get_api_key(self, __user__: dict) -> str:
        return __user__["valves"].last_fm_api_key

    def _get_username(self, __user__: dict, user: Optional[str] = None) -> Optional[str]:
        return user or __user__["valves"].last_fm_api_user

    def _make_request(self, api_key: str, method: str, params: dict) -> dict[str, Any]:
        """Internal helper to call Last.fm API."""
        if not api_key:
            raise RuntimeError("Last.fm API key not provided.")
        url = "https://ws.audioscrobbler.com/2.0/"
        params.update(
            {
                "method": method,
                "api_key": api_key,
                "format": "json",
            }
        )
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

        except requests.RequestException as e:
            raise RuntimeError(f"Request failed: {e}") from e
        except ValueError as e:
            raise RuntimeError(f"Invalid JSON response: {e}") from e
        if "error" in data:
            raise RuntimeError(f"API error: {data.get('error', 'unknown')}")

        return data

    def _extract_image_url(self, data: dict, size: str = "medium") -> str:
        image_url = ""
        if "image" in data and isinstance(data["image"], list):
            for img in data["image"]:
                if img.get("size") == size:
                    image_url = img.get("#text", "")
                    break
            if not image_url and data["image"]:
                image_url = data["image"][0].get("#text", "")
        return image_url

    # ------------------------------------------------------------------ #
    # Rich UI helpers
    # ------------------------------------------------------------------ #

    def _rich_enabled(self, __user__: dict) -> bool:
        """True when the user turned on the enable_rich_responses valve."""
        valves = (__user__ or {}).get("valves")
        if isinstance(valves, dict):
            return bool(valves.get("enable_rich_responses", False))
        return bool(getattr(valves, "enable_rich_responses", False))

    @staticmethod
    def _esc(value: Any) -> str:
        return html_lib.escape(str(value), quote=True)

    @staticmethod
    def _safe_url(url: Any) -> str:
        """Only allow http(s) URLs into href/src attributes."""
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return url
        return ""

    @staticmethod
    def _fmt_num(value: Any) -> str:
        try:
            return f"{int(value):,}"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _clean_summary(summary: str) -> str:
        """Strip Last.fm's embedded HTML (e.g. the 'Read more' link) from a wiki summary."""
        text = re.sub(r"<[^>]+>", "", summary or "")
        return html_lib.unescape(text).strip()

    def _rich_image(self, data: dict, size: str = "medium") -> str:
        """Image URL suitable for display, or '' for missing/placeholder images."""
        url = self._extract_image_url(data, size)
        if not url or _LASTFM_PLACEHOLDER_HASH in url:
            return ""
        return self._safe_url(url)

    def _wrap_html(self, body: str) -> str:
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<style>"
            + _RICH_CSS
            + "</style></head><body>"
            + body
            + "<script>"
            + _RICH_SCRIPT
            + "</script></body></html>"
        )

    def _rich_response(self, body: str, context: str) -> tuple:
        """
        Build the (HTMLResponse, context) tuple Open WebUI turns into an inline embed.
        The context string is what the LLM sees instead of the generic
        "Embedded UI result is active" message, so it still has the actual data.
        """
        note = (
            "A rich UI card with these results is already displayed to the user. "
            "Comment on or summarize it rather than repeating every item.\n\n"
        )
        return (
            HTMLResponse(
                content=self._wrap_html(body),
                headers={"Content-Disposition": "inline"},
            ),
            note + context,
        )

    def _render_list(
        self,
        title: str,
        subtitle: str,
        items: list[dict],
        max_rows: int = 25,
    ) -> str:
        """
        Ranked list card. Each item may contain:
        title, subtitle, url, image, meta (list[str]), badge (str),
        bar (float 0-1), prompt (str, adds an 'Ask' button that fills the chat box).
        """
        esc = self._esc
        rows = []
        for i, it in enumerate(items[:max_rows], 1):
            url = self._safe_url(it.get("url"))
            name = esc(it.get("title", "Unknown"))
            title_html = (
                f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{name}</a>'
                if url
                else name
            )
            badge = (
                f'<span class="badge">{esc(it["badge"])}</span>'
                if it.get("badge")
                else ""
            )
            thumb = (
                f'<img class="thumb" src="{esc(it["image"])}" alt="" loading="lazy">'
                if it.get("image")
                else ""
            )
            sub = (
                f'<div class="sub">{esc(it["subtitle"])}</div>'
                if it.get("subtitle")
                else ""
            )
            meta = (
                '<div class="meta">'
                + "".join(f'<span class="chip">{esc(m)}</span>' for m in it["meta"])
                + "</div>"
                if it.get("meta")
                else ""
            )
            bar = ""
            if it.get("bar") is not None:
                pct = max(0, min(100, round(float(it["bar"]) * 100)))
                bar = f'<div class="bar"><span style="width:{pct}%"></span></div>'
            ask = (
                f'<button class="ask" type="button" title="Ask about this" '
                f'data-prompt="{esc(it["prompt"])}">Ask</button>'
                if it.get("prompt")
                else ""
            )
            rows.append(
                f'<li class="row"><span class="rank">{i}</span>{thumb}'
                f'<div class="main"><div class="title">{title_html}{badge}</div>'
                f"{sub}{meta}{bar}</div>{ask}</li>"
            )

        footer = ""
        if len(items) > max_rows:
            footer = f'<div class="foot">Showing top {max_rows} of {len(items)}.</div>'
        head_sub = f"<p>{esc(subtitle)}</p>" if subtitle else ""
        return (
            f'<div class="card"><div class="head"><h1>{esc(title)}</h1>{head_sub}</div>'
            f'<ol>{"".join(rows)}</ol>{footer}</div>'
        )

    def _render_card(
        self,
        title: str,
        subtitle: str = "",
        image: str = "",
        stats: Optional[list[tuple]] = None,
        tags: Optional[list[str]] = None,
        summary: str = "",
        url: str = "",
    ) -> str:
        """Detail card for a single album / artist / track / user."""
        esc = self._esc
        img = f'<img src="{esc(image)}" alt="">' if image else ""
        sub = f'<p class="sub">{esc(subtitle)}</p>' if subtitle else ""
        stats_html = ""
        if stats:
            stats_html = (
                '<div class="stats">'
                + "".join(
                    f'<div class="stat"><b>{esc(v)}</b><span>{esc(k)}</span></div>'
                    for k, v in stats
                )
                + "</div>"
            )
        tags_html = ""
        if tags:
            tags_html = (
                '<div class="tags">'
                + "".join(f'<span class="chip">{esc(t)}</span>' for t in tags if t)
                + "</div>"
            )
        summary_html = (
            f'<p class="summary">{esc(self._clean_summary(summary))}</p>'
            if summary
            else ""
        )
        safe = self._safe_url(url)
        link = (
            f'<div class="foot"><a href="{esc(safe)}" target="_blank" '
            f'rel="noopener noreferrer">View on Last.fm ↗</a></div>'
            if safe
            else ""
        )
        return (
            f'<div class="card"><div class="hero">{img}<div><h1>{esc(title)}</h1>{sub}'
            f"{tags_html}</div></div>{stats_html}{summary_html}{link}</div>"
        )

    # ------------------------------------------------------------------ #
    # album methods
    # ------------------------------------------------------------------ #

    def get_album_info(
        self,
        __user__: dict,
        artist: Annotated[str, Field(description="Artist name")],
        album: Annotated[str, Field(description="Album name")],
        mbid: Annotated[
            Optional[str],
            Field(
                description="MusicBrainz ID for the album. If provided, artist and album are ignored."
            ),
        ] = None,
    ) -> Union[str, tuple]:
        """Return information about a specific album."""
        try:
            api_key = self._get_api_key(__user__)
            params = {"mbid": mbid} if mbid else {"artist": artist, "album": album}
            data = self._make_request(api_key, "album.getInfo", params)
        except RuntimeError as exc:
            return f"Error: {exc}"
        album_data = data.get("album", {})
        if not album_data:
            return "No album information found. Please check the artist and album names, or provide a valid MBID."
        name = album_data.get("name", "Unknown")
        artist_name = album_data.get("artist", "Unknown")
        mbid_val = album_data.get("mbid", "N/A")
        url = album_data.get("url", "#")
        listeners = album_data.get("listeners", "0")
        playcount = album_data.get("playcount", "0")
        # Extract wiki summary if available
        wiki_summary = ""
        if "wiki" in album_data and album_data["wiki"]:
            wiki_summary = album_data["wiki"].get("summary", "")
            # Truncate summary to first 500 characters for brevity
            if len(wiki_summary) > 500:
                wiki_summary = wiki_summary[:500] + "..."
        lines = [
            f"### Album Info: {name} by {artist_name}",
            f"- **MBID:** {mbid_val}",
            f"- **URL:** [{url}]({url})",
            f"- **Listeners:** {listeners}",
            f"- **Playcount:** {playcount}",
        ]
        if wiki_summary:
            lines.append(f"- **Summary:** {wiki_summary}")
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_card(
                title=name,
                subtitle=f"by {artist_name}",
                image=self._rich_image(album_data, "extralarge")
                or self._rich_image(album_data, "large"),
                stats=[
                    ("Listeners", self._fmt_num(listeners)),
                    ("Plays", self._fmt_num(playcount)),
                ],
                summary=wiki_summary,
                url=url,
            )
            return self._rich_response(body, text)
        return text

    def album_search(
        self,
        __user__: dict,
        album: Annotated[str, Field(description="Album name to search for")],
        artist: Annotated[
            Optional[str],
            Field(description="Artist name to narrow the search (optional)"),
        ] = None,
        limit: int = Field(
            default=5,
            description="Number of results to return (1-10).",
            ge=1,
            le=10,
        ),
    ) -> Union[str, tuple]:
        """Search for albums by name using the Last.fm album.search API."""
        try:
            api_key = self._get_api_key(__user__)
            params = {
                "album": album,
                "limit": limit,
                **({"artist": artist} if artist else {}),
            }
            data = self._make_request(api_key, "album.search", params)
        except RuntimeError as exc:
            return f"Error: {exc}"
        results = data.get("results", {})
        matches = results.get("albummatches", {}).get("album", [])
        if not matches:
            return f"No albums found matching '{album}'."
        # Ensure it's a list (API returns dict for single result)
        matches = [matches] if isinstance(matches, dict) else matches
        lines = [f"### Album Search Results for '{album}'\n"]
        items = []
        for i, m in enumerate(matches, 1):
            name = m.get("name", "Unknown")
            artist_name = m.get("artist", "Unknown")
            mbid = m.get("mbid", "N/A")
            url = m.get("url", "#")
            lines.append(f"{i}. **{name}** by *{artist_name}* (MBID: {mbid}) – [{url}]({url})")
            items.append(
                {
                    "title": name,
                    "subtitle": artist_name,
                    "url": url,
                    "image": self._rich_image(m),
                    "prompt": f"Tell me about the album {name} by {artist_name}",
                }
            )
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_list(f"Album results for “{album}”", "", items)
            return self._rich_response(body, text)
        return text

    # ------------------------------------------------------------------ #
    # artist methods
    # ------------------------------------------------------------------ #

    def get_artist_similar(
        self,
        __user__: dict,
        artist: Annotated[str, Field(description="Artist name")],
        mbid: Annotated[
            Optional[str],
            Field(
                description="MusicBrainz ID for the artist. If provided, artist parameter is ignored."
            ),
        ] = None,
        limit: int = Field(
            default=5,
            description="Number of similar artists to return (1-10).",
            ge=1,
            le=10,
        ),
    ) -> Union[str, tuple]:
        """Return similar artists to a given artist."""
        try:
            api_key = self._get_api_key(__user__)
            params = {"mbid": mbid} if mbid else {"artist": artist, "limit": limit}
            data = self._make_request(api_key, "artist.getSimilar", params)
        except RuntimeError as exc:
            return f"Error: {exc}"
        if "similarartists" not in data or "artist" not in data["similarartists"]:
            return "No similar artists data returned."
        similar_artists = data["similarartists"]["artist"]
        if not similar_artists:
            return "No similar artists found."
        # Ensure it's a list (API returns dict for single item?)
        similar_artists = (
            [similar_artists] if isinstance(similar_artists, dict) else similar_artists
        )
        lines = [f"### Similar Artists to {artist}\n"]
        items = []
        for i, sim_artist in enumerate(similar_artists, 1):
            name = sim_artist.get("name", "Unknown")
            mbid_val = sim_artist.get("mbid", "N/A")
            match = sim_artist.get("match", "0")  # similarity score
            url = sim_artist.get("url", "#")
            lines.append(f"{i}. **{name}** (MBID: {mbid_val}, match score: {match}) – [{url}]({url})")
            try:
                score = float(match)
            except (TypeError, ValueError):
                score = 0.0
            items.append(
                {
                    "title": name,
                    "url": url,
                    "image": self._rich_image(sim_artist),
                    "meta": [f"{round(score * 100)}% match"],
                    "bar": score,
                    "prompt": f"Tell me about the artist {name}",
                }
            )
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_list(f"Similar to {artist}", "", items)
            return self._rich_response(body, text)
        return text

    def artist_search(
        self,
        __user__: dict,
        artist: Annotated[str, Field(description="Artist name to search for")],
        limit: int = Field(
            default=5,
            description="Number of results to return (1-10).",
            ge=1,
            le=10,
        ),
    ) -> Union[str, tuple]:
        """Search for artists by name using the Last.fm artist.search API."""
        try:
            api_key = self._get_api_key(__user__)
            params = {"artist": artist, "limit": limit}
            data = self._make_request(api_key, "artist.search", params)
        except RuntimeError as exc:
            return f"Error: {exc}"
        results = data.get("results", {})
        matches = results.get("artistmatches", {}).get("artist", [])
        if not matches:
            return f"No artists found matching '{artist}'."
        # Ensure it's a list (API returns dict for single result)
        matches = [matches] if isinstance(matches, dict) else matches
        lines = [f"### Artist Search Results for '{artist}'\n"]
        items = []
        for i, m in enumerate(matches, 1):
            name = m.get("name", "Unknown")
            mbid = m.get("mbid", "N/A")
            url = m.get("url", "#")
            lines.append(f"{i}. **{name}** (MBID: {mbid}) – [{url}]({url})")
            listeners = m.get("listeners")
            items.append(
                {
                    "title": name,
                    "url": url,
                    "image": self._rich_image(m),
                    "meta": (
                        [f"{self._fmt_num(listeners)} listeners"] if listeners else []
                    ),
                    "prompt": f"Tell me about the artist {name}",
                }
            )
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_list(f"Artist results for “{artist}”", "", items)
            return self._rich_response(body, text)
        return text

    def get_artist_info(
        self,
        __user__: dict,
        artist: Annotated[str, Field(description="Artist name")],
        mbid: Annotated[
            Optional[str],
            Field(
                description="MusicBrainz ID for the artist. If provided, artist parameter is ignored."
            ),
        ] = None,
    ) -> Union[str, tuple]:
        """Return information about a specific artist."""
        try:
            api_key = self._get_api_key(__user__)
            params = {"mbid": mbid} if mbid else {"artist": artist}
            data = self._make_request(api_key, "artist.getinfo", params)
        except RuntimeError as exc:
            return f"Error: {exc}"
        if "artist" not in data:
            return "No artist data returned."
        artist_data = data["artist"]
        name = artist_data.get("name", "Unknown")
        mbid_val = artist_data.get("mbid", "N/A")
        url = artist_data.get("url", "#")
        stats = artist_data.get("stats", {})
        listeners = stats.get("listeners", "0")
        playcount = stats.get("playcount", "0")
        # Extract wiki summary if available
        wiki_summary = ""
        if "wiki" in artist_data and artist_data["wiki"]:
            wiki_summary = artist_data["wiki"].get("summary", "")
            if len(wiki_summary) > 500:
                wiki_summary = wiki_summary[:500] + "..."
        # Extract tags if available
        tags = []
        if "tags" in artist_data and artist_data["tags"]:
            tag_list = artist_data["tags"].get("tag", [])
            if isinstance(tag_list, dict):
                tag_list = [tag_list]
            for tag in tag_list[:5]:
                tags.append(tag.get("name", ""))
        lines = [
            f"### Artist Info: {name}",
            f"- **MBID:** {mbid_val}",
            f"- **URL:** [{url}]({url})",
            f"- **Listeners:** {listeners}",
            f"- **Playcount:** {playcount}",
        ]
        if tags:
            lines.append(f"- **Tags:** {', '.join(tags)}")
        if wiki_summary:
            lines.append(f"- **Summary:** {wiki_summary}")
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_card(
                title=name,
                image=self._rich_image(artist_data, "large"),
                stats=[
                    ("Listeners", self._fmt_num(listeners)),
                    ("Plays", self._fmt_num(playcount)),
                ],
                tags=tags,
                summary=wiki_summary,
                url=url,
            )
            return self._rich_response(body, text)
        return text

    def get_artist_top_albums(
        self,
        __user__: dict,
        artist: Annotated[str, Field(description="Artist name")],
        mbid: Annotated[
            Optional[str],
            Field(
                description="MusicBrainz ID for the artist. If provided, artist parameter is ignored."
            ),
        ] = None,
        limit: int = Field(
            default=5,
            description="Number of top albums to return (1-10).",
            ge=1,
            le=10,
        ),
    ) -> Union[str, tuple]:
        """Return an artist's top albums."""
        try:
            api_key = self._get_api_key(__user__)
            params = {"mbid": mbid} if mbid else {"artist": artist, "limit": limit}
            data = self._make_request(api_key, "artist.gettopalbums", params)
        except RuntimeError as exc:
            return f"Error: {exc}"
        if "topalbums" not in data or "album" not in data["topalbums"]:
            return "No album data returned."
        albums = data["topalbums"]["album"]
        if not albums:
            return "No albums found for this artist."
        albums = [albums] if isinstance(albums, dict) else albums
        lines = [f"### Top {len(albums)} Albums for {artist}\n"]
        items = []
        for i, a in enumerate(albums, 1):
            name = a.get("name", "Unknown")
            playcount = a.get("playcount", "0")
            mbid_val = a.get("mbid", "N/A")
            url = a.get("url", "#")
            lines.append(f"{i}. **{name}** ({playcount} plays) (MBID: {mbid_val}) – [{url}]({url})")
            items.append(
                {
                    "title": name,
                    "url": url,
                    "image": self._rich_image(a),
                    "meta": [f"{self._fmt_num(playcount)} plays"],
                    "prompt": f"Tell me about the album {name} by {artist}",
                }
            )
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_list(f"Top albums: {artist}", "", items)
            return self._rich_response(body, text)
        return text

    def get_artist_top_tracks(
        self,
        __user__: dict,
        artist: Annotated[str, Field(description="Artist name")],
        mbid: Annotated[
            Optional[str],
            Field(
                description="MusicBrainz ID for the artist. If provided, artist parameter is ignored."
            ),
        ] = None,
        limit: int = Field(
            default=5,
            description="Number of top tracks to return (1-10).",
            ge=1,
            le=10,
        ),
    ) -> Union[str, tuple]:
        """Return an artist's top tracks."""
        try:
            api_key = self._get_api_key(__user__)
            params = {"mbid": mbid} if mbid else {"artist": artist, "limit": limit}
            data = self._make_request(api_key, "artist.gettoptracks", params)
        except RuntimeError as exc:
            return f"Error: {exc}"
        if "toptracks" not in data or "track" not in data["toptracks"]:
            return "No track data returned."
        tracks = data["toptracks"]["track"]
        if not tracks:
            return "No tracks found for this artist."
        tracks = [tracks] if isinstance(tracks, dict) else tracks
        lines = [f"### Top {len(tracks)} Tracks for {artist}\n"]
        items = []
        for i, t in enumerate(tracks, 1):
            name = t.get("name", "Unknown")
            playcount = t.get("playcount", "0")
            mbid_val = t.get("mbid", "N/A")
            url = t.get("url", "#")
            lines.append(f"{i}. **{name}** ({playcount} plays) (MBID: {mbid_val}) – [{url}]({url})")
            items.append(
                {
                    "title": name,
                    "url": url,
                    "image": self._rich_image(t),
                    "meta": [f"{self._fmt_num(playcount)} plays"],
                    "prompt": f"Tell me about the track {name} by {artist}",
                }
            )
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_list(f"Top tracks: {artist}", "", items)
            return self._rich_response(body, text)
        return text

    # ------------------------------------------------------------------ #
    # track methods
    # ------------------------------------------------------------------ #

    def get_track_info(
        self,
        __user__: dict,
        artist: Annotated[str, Field(description="Artist name")],
        track: Annotated[str, Field(description="Track name")],
        mbid: Annotated[
            Optional[str],
            Field(
                description="MusicBrainz ID for the track. If provided, artist and track are ignored."
            ),
        ] = None,
    ) -> Union[str, tuple]:
        """Return information about a specific track."""
        try:
            api_key = self._get_api_key(__user__)
            params = {"mbid": mbid} if mbid else {"artist": artist, "track": track}
            data = self._make_request(api_key, "track.getInfo", params)
        except RuntimeError as exc:
            return f"Error: {exc}"
        if "track" not in data:
            return "No track data returned."
        track_data = data["track"]
        name = track_data.get("name", "Unknown")
        artist_name = track_data.get("artist", {}).get("name", "Unknown")
        mbid_val = track_data.get("mbid", "N/A")
        url = track_data.get("url", "#")
        duration_str = track_data.get("duration", "0")  # in milliseconds
        listeners = track_data.get("listeners", "0")
        playcount = track_data.get("playcount", "0")
        # Extract wiki summary if available
        wiki_summary = ""
        if "wiki" in track_data and track_data["wiki"]:
            wiki_summary = track_data["wiki"].get("summary", "")
            if len(wiki_summary) > 500:
                wiki_summary = wiki_summary[:500] + "..."
        # Safely convert duration to seconds
        try:
            duration_seconds = (
                int(duration_str) // 1000 if duration_str.isdigit() else "N/A"
            )
        except (AttributeError, ValueError):
            duration_seconds = "N/A"
        lines = [
            f"### Track Info: {name} by {artist_name}",
            f"- **MBID:** {mbid_val}",
            f"- **URL:** [{url}]({url})",
            f"- **Duration:** {duration_seconds} seconds",
            f"- **Listeners:** {listeners}",
            f"- **Playcount:** {playcount}",
        ]
        if wiki_summary:
            lines.append(f"- **Summary:** {wiki_summary}")
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            stats = []
            if isinstance(duration_seconds, int) and duration_seconds > 0:
                stats.append(
                    (
                        "Duration",
                        f"{duration_seconds // 60}:{duration_seconds % 60:02d}",
                    )
                )
            stats += [
                ("Listeners", self._fmt_num(listeners)),
                ("Plays", self._fmt_num(playcount)),
            ]
            album_info = track_data.get("album") or {}
            body = self._render_card(
                title=name,
                subtitle=f"by {artist_name}"
                + (f" · {album_info['title']}" if album_info.get("title") else ""),
                image=self._rich_image(album_info, "large"),
                stats=stats,
                summary=wiki_summary,
                url=url,
            )
            return self._rich_response(body, text)
        return text

    def get_track_similar(
        self,
        __user__: dict,
        artist: Annotated[str, Field(description="Artist name")],
        track: Annotated[str, Field(description="Track name")],
        limit: Annotated[
            int,
            Field(
                default=5,
                description="Number of similar tracks to return (1-10).",
                ge=1,
                le=10,
            ),
        ],
        mbid: Annotated[
            Optional[str],
            Field(
                description="MusicBrainz ID for the track. If provided, artist and track are ignored."
            ),
        ] = None,
    ) -> Union[str, tuple]:
        """Return similar tracks to a given track."""
        try:
            api_key = self._get_api_key(__user__)
            params = (
                {"mbid": mbid}
                if mbid
                else {"artist": artist, "track": track, "limit": limit}
            )
            data = self._make_request(api_key, "track.getSimilar", params)
        except RuntimeError as exc:
            return f"Error: {exc}"
        if "similartracks" not in data or "track" not in data["similartracks"]:
            return "No similar tracks data returned."
        similar_tracks = data["similartracks"]["track"]
        if not similar_tracks:
            return "No similar tracks found."
        # Ensure it's a list
        similar_tracks = (
            [similar_tracks] if isinstance(similar_tracks, dict) else similar_tracks
        )
        lines = [f"### Similar Tracks to {track} by {artist}\n"]
        items = []
        for i, sim_track in enumerate(similar_tracks, 1):
            name = sim_track.get("name", "Unknown")
            artist_name = sim_track.get("artist", {}).get("name", "Unknown")
            match = sim_track.get("match", "0")
            lines.append(f"{i}. {name} – {artist_name} (match: {match})")
            try:
                score = float(match)
            except (TypeError, ValueError):
                score = 0.0
            items.append(
                {
                    "title": name,
                    "subtitle": artist_name,
                    "url": sim_track.get("url"),
                    "image": self._rich_image(sim_track),
                    "meta": [f"{round(score * 100)}% match"],
                    "bar": score,
                    "prompt": f"Tell me about the track {name} by {artist_name}",
                }
            )
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_list(f"Similar to {track}", f"by {artist}", items)
            return self._rich_response(body, text)
        return text

    def track_search(
        self,
        __user__: dict,
        track: Annotated[str, Field(description="Track name to search for")],
        artist: Annotated[
            Optional[str],
            Field(description="Artist name to narrow the search (optional)"),
        ] = None,
        limit: int = Field(
            default=5,
            description="Number of results to return (1-10).",
            ge=1,
            le=10,
        ),
    ) -> Union[str, tuple]:
        """Search for tracks by name using the Last.fm track.search API."""
        try:
            api_key = self._get_api_key(__user__)
            params = {
                "track": track,
                "limit": limit,
                **({"artist": artist} if artist else {}),
            }
            data = self._make_request(api_key, "track.search", params)
        except RuntimeError as exc:
            return f"Error: {exc}"
        results = data.get("results", {})
        matches = results.get("trackmatches", {}).get("track", [])
        if not matches:
            return f"No tracks found matching '{track}'."
        # Ensure it's a list (API returns dict for single result)
        matches = [matches] if isinstance(matches, dict) else matches
        lines = [f"### Track Search Results for '{track}'\n"]
        items = []
        for i, m in enumerate(matches, 1):
            name = m.get("name", "Unknown")
            artist_name = m.get("artist", "Unknown")
            mbid = m.get("mbid", "N/A")
            url = m.get("url", "#")
            lines.append(f"{i}. **{name}** by *{artist_name}* (MBID: {mbid}) – [{url}]({url})")
            listeners = m.get("listeners")
            items.append(
                {
                    "title": name,
                    "subtitle": artist_name,
                    "url": url,
                    "image": self._rich_image(m),
                    "meta": (
                        [f"{self._fmt_num(listeners)} listeners"] if listeners else []
                    ),
                    "prompt": f"Tell me about the track {name} by {artist_name}",
                }
            )
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_list(f"Track results for “{track}”", "", items)
            return self._rich_response(body, text)
        return text

    # ------------------------------------------------------------------ #
    # user methods
    # ------------------------------------------------------------------ #

    def get_user_info(
        self,
        __user__: dict,
        user: Annotated[
            Optional[str],
            Field(
                description="Last.fm username. If not provided, the default user from the valves will be used."
            ),
        ] = None,
    ) -> Union[str, tuple]:
        """Return information about a specific user."""
        try:
            api_key = self._get_api_key(__user__)
            params = {"user": self._get_username(__user__, user) or ""}
            data = self._make_request(api_key, "user.getInfo", params)
        except RuntimeError as exc:
            return f"Error: {exc}"
        if "user" not in data:
            return "No user data returned."
        user_data = data["user"]
        name = user_data.get("name", "Unknown")
        realname = user_data.get("realname", "N/A")
        country = user_data.get("country", "N/A")
        age = user_data.get("age", "N/A")
        gender = user_data.get("gender", "N/A")
        subscriber = user_data.get("subscriber", "0")
        playcount = user_data.get("playcount", "0")
        playlist_count = user_data.get("playlist_count", "0")
        registered = user_data.get("registered", {}).get("#text", "N/A")
        url = user_data.get("url", "#")
        image_url = self._extract_image_url(user_data)
        lines = [
            f"### User Info: {name}",
            f"- **Realname:** {realname}",
            f"- **Country:** {country}",
            f"- **Age:** {age}",
            f"- **Gender:** {gender}",
            f"- **Subscriber:** {'Yes' if subscriber == '1' else 'No'}",
            f"- **Playcount:** {playcount}",
            f"- **Playlist Count:** {playlist_count}",
            f"- **Registered:** {registered}",
            f"- **URL:** [{url}]({url})",
        ]
        if image_url:
            lines.append(f"- **Avatar:** ![Avatar]({image_url})")
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            stats = [("Scrobbles", self._fmt_num(playcount))]
            if str(playlist_count) not in ("0", "N/A", ""):
                stats.append(("Playlists", self._fmt_num(playlist_count)))
            if country not in ("N/A", "None", ""):
                stats.append(("Country", country))
            if str(registered) not in ("N/A", ""):
                stats.append(("Registered", str(registered)))
            body = self._render_card(
                title=name,
                subtitle=realname if realname not in ("N/A", "") else "",
                image=self._safe_url(self._extract_image_url(user_data, "large")),
                stats=stats,
                tags=["Subscriber"] if subscriber == "1" else [],
                url=url,
            )
            return self._rich_response(body, text)
        return text

    def get_top_albums(
        self,
        __user__: dict,
        limit: Annotated[
            int,
            Field(
                default=5,
                description="Number of items to return (1-10).",
                ge=1,
                le=10,
            ),
        ],
    ) -> Union[str, tuple]:
        """Return list of the user's top albums."""
        api_key = self._get_api_key(__user__)
        username = self._get_username(__user__)
        if not username:
            return "Error: Last.fm username not provided."
        try:
            data = self._make_request(api_key, "user.gettopalbums", {"user": username, "limit": limit})
        except RuntimeError as exc:
            return f"Error: {exc}"
        if "topalbums" not in data or "album" not in data["topalbums"]:
            return "No album data returned."
        albums = data["topalbums"]["album"]
        if not albums:
            return "No albums found for this user."
        lines = [f"### Top {len(albums)} Albums for {username}\n"]
        items = []
        for i, album in enumerate(albums, 1):
            name = album.get("name", "Unknown")
            artist = album.get("artist", {}).get("name", "Unknown")
            playcount = album.get("playcount", "0")
            lines.append(f"{i}. **{name}** by *{artist}* ({playcount} plays)")
            items.append(
                {
                    "title": name,
                    "subtitle": artist,
                    "url": album.get("url"),
                    "image": self._rich_image(album),
                    "meta": [f"{self._fmt_num(playcount)} plays"],
                }
            )
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_list(f"Top albums", f"{username}", items)
            return self._rich_response(body, text)
        return text

    def get_top_tracks(
        self,
        __user__: dict,
        limit: Annotated[
            int,
            Field(
                default=5,
                description="Number of items to return (1-10).",
                ge=1,
                le=10,
            ),
        ],
    ) -> Union[str, tuple]:
        """Return a formatted list of the user's top (most listened to) tracks."""
        api_key = self._get_api_key(__user__)
        username = self._get_username(__user__)
        if not username:
            return "Error: Last.fm username not provided."
        try:
            data = self._make_request(api_key, "user.gettoptracks", {"user": username, "limit": limit})
        except RuntimeError as exc:
            return f"Error: {exc}"
        if "toptracks" not in data or "track" not in data["toptracks"]:
            return "No track data returned."
        tracks = data["toptracks"]["track"]
        if not tracks:
            return "No tracks found for this user."
        lines = [f"### Top {len(tracks)} Tracks for {username} (Playlist)\n"]
        items = []
        for i, track in enumerate(tracks, 1):
            name = track.get("name", "Unknown")
            artist = track.get("artist", {}).get("name", "Unknown")
            playcount = track.get("playcount", "0")
            lines.append(f"{i}. {name} – {artist} ({playcount} plays)")
            items.append(
                {
                    "title": name,
                    "subtitle": artist,
                    "url": track.get("url"),
                    "image": self._rich_image(track),
                    "meta": [f"{self._fmt_num(playcount)} plays"],
                }
            )
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_list("Top tracks", f"{username}", items)
            return self._rich_response(body, text)
        return text

    def get_recent_tracks(
        self,
        __user__: dict,
        user: Annotated[
            Optional[str],
            Field(
                description="Last.fm username. If not provided, the default user from the valves will be used."
            ),
        ] = None,
        limit: int = Field(
            default=5,
            description="Number of recent tracks to return (1-10).",
            ge=1,
            le=10,
        ),
    ) -> Union[str, tuple]:
        """Return the user's recently played tracks."""
        api_key = self._get_api_key(__user__)
        username = self._get_username(__user__, user)
        if not username:
            return "Error: Last.fm username not provided."
        params = {"user": username, "limit": limit}
        try:
            data = self._make_request(api_key, "user.getrecenttracks", params)
        except RuntimeError as exc:
            return f"Error: {exc}"
        if "recenttracks" not in data or "track" not in data["recenttracks"]:
            return "No recent tracks data returned."
        tracks = data["recenttracks"]["track"]
        if not tracks:
            return "No recent tracks found for this user."
        tracks = [tracks] if isinstance(tracks, dict) else tracks
        lines = [f"### Recent Tracks for {username}\n"]
        items = []
        for i, track in enumerate(tracks, 1):
            name = track.get("name", "Unknown")
            artist_val = track.get("artist", "Unknown")
            artist = (
                artist_val.get("name", "Unknown")
                if isinstance(artist_val, dict)
                else artist_val
            )
            album_val = track.get("album", "Unknown")
            album = (
                album_val.get("#text", "Unknown")
                if isinstance(album_val, dict)
                else album_val
            )
            url = track.get("url", "#")
            now_playing = (track.get("@attr") or {}).get("nowplaying") == "true"
            date = ""
            if track.get("date") and isinstance(track["date"], dict):
                date = track["date"].get("#text", "")
            elif now_playing:
                date = "Now playing"
            line = f"{i}. **{name}** by *{artist}*"
            if album and album != "Unknown":
                line += f" (from *{album}*)"
            if date:
                line += f" — {date}"
            line += f" – [{url}]({url})"
            lines.append(line)
            subtitle = artist
            if album and album != "Unknown":
                subtitle += f" · {album}"
            items.append(
                {
                    "title": name,
                    "subtitle": subtitle,
                    "url": url,
                    "image": self._rich_image(track),
                    "meta": [date] if date and not now_playing else [],
                    "badge": "Now playing" if now_playing else "",
                }
            )
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_list("Recent tracks", f"{username}", items)
            return self._rich_response(body, text)
        return text

    def get_user_top_artists(
        self,
        __user__: dict,
        user: Annotated[
            Optional[str],
            Field(
                description="Last.fm username. If not provided, the default user from the valves will be used."
            ),
        ] = None,
        limit: int = Field(
            default=5,
            description="Number of top artists to return (1-10).",
            ge=1,
            le=10,
        ),
    ) -> Union[str, tuple]:
        """Return the user's top (most listened to) artists."""
        api_key = self._get_api_key(__user__)
        username = self._get_username(__user__, user)
        if not username:
            return "Error: Last.fm username not provided."
        try:
            data = self._make_request(api_key, "user.gettopartists", {"user": username, "limit": limit})
        except RuntimeError as exc:
            return f"Error: {exc}"
        if "topartists" not in data or "artist" not in data["topartists"]:
            return "No artist data returned."
        artists = data["topartists"]["artist"]
        if not artists:
            return "No artists found for this user."
        artists = [artists] if isinstance(artists, dict) else artists
        lines = [f"### Top {len(artists)} Artists for {username}\n"]
        items = []
        for i, a in enumerate(artists, 1):
            name = a.get("name", "Unknown")
            playcount = a.get("playcount", "0")
            mbid = a.get("mbid", "N/A")
            url = a.get("url", "#")
            lines.append(f"{i}. **{name}** ({playcount} plays) (MBID: {mbid}) – [{url}]({url})")
            items.append(
                {
                    "title": name,
                    "url": url,
                    "image": self._rich_image(a),
                    "meta": [f"{self._fmt_num(playcount)} plays"],
                    "prompt": f"Tell me about the artist {name}",
                }
            )
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_list("Top artists", f"{username}", items)
            return self._rich_response(body, text)
        return text

    def get_user_weekly_artist_chart(
        self,
        __user__: dict,
        user: Annotated[
            Optional[str],
            Field(
                description="Last.fm username. If not provided, the default user from the valves will be used."
            ),
        ] = None,
    ) -> Union[str, tuple]:
        """Return the user's weekly artist chart."""
        api_key = self._get_api_key(__user__)
        username = self._get_username(__user__, user)
        if not username:
            return "Error: Last.fm username not provided."
        try:
            data = self._make_request(api_key, "user.getweeklyartistchart", {"user": username})
        except RuntimeError as exc:
            return f"Error: {exc}"
        if "weeklyartistchart" not in data or "artist" not in data["weeklyartistchart"]:
            return "No weekly artist chart data returned."
        artists = data["weeklyartistchart"]["artist"]
        if not artists:
            return "No artists found in this user's weekly chart."
        artists = [artists] if isinstance(artists, dict) else artists
        lines = [f"### Weekly Artist Chart for {username}\n"]
        items = []
        for i, a in enumerate(artists, 1):
            name = a.get("name", "Unknown")
            playcount = a.get("playcount", "0")
            mbid = a.get("mbid", "N/A")
            url = a.get("url", "#")
            lines.append(f"{i}. **{name}** ({playcount} plays) (MBID: {mbid}) – [{url}]({url})")
            items.append(
                {
                    "title": name,
                    "url": url,
                    "meta": [f"{self._fmt_num(playcount)} plays"],
                }
            )
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_list("Weekly artist chart", f"{username}", items)
            return self._rich_response(body, text)
        return text

    def get_user_weekly_album_chart(
        self,
        __user__: dict,
        user: Annotated[
            Optional[str],
            Field(
                description="Last.fm username. If not provided, the default user from the valves will be used."
            ),
        ] = None,
    ) -> Union[str, tuple]:
        """Return the user's weekly album chart."""
        api_key = self._get_api_key(__user__)
        username = self._get_username(__user__, user)
        if not username:
            return "Error: Last.fm username not provided."
        try:
            data = self._make_request(api_key, "user.getweeklyalbumchart", {"user": username})
        except RuntimeError as exc:
            return f"Error: {exc}"
        if "weeklyalbumchart" not in data or "album" not in data["weeklyalbumchart"]:
            return "No weekly album chart data returned."
        albums = data["weeklyalbumchart"]["album"]
        if not albums:
            return "No albums found in this user's weekly chart."
        albums = [albums] if isinstance(albums, dict) else albums
        lines = [f"### Weekly Album Chart for {username}\n"]
        items = []
        for i, a in enumerate(albums, 1):
            name = a.get("name", "Unknown")
            artist_val = a.get("artist", "Unknown")
            artist = (
                artist_val.get("name", "Unknown")
                if isinstance(artist_val, dict)
                else artist_val
            )
            playcount = a.get("playcount", "0")
            mbid = a.get("mbid", "N/A")
            url = a.get("url", "#")
            lines.append(f"{i}. **{name}** by *{artist}* ({playcount} plays) (MBID: {mbid}) – [{url}]({url})")
            items.append(
                {
                    "title": name,
                    "subtitle": artist,
                    "url": url,
                    "meta": [f"{self._fmt_num(playcount)} plays"],
                }
            )
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_list("Weekly album chart", f"{username}", items)
            return self._rich_response(body, text)
        return text

    def get_user_weekly_track_chart(
        self,
        __user__: dict,
        user: Annotated[
            Optional[str],
            Field(
                description="Last.fm username. If not provided, the default user from the valves will be used."
            ),
        ] = None,
    ) -> Union[str, tuple]:
        """Return the user's weekly track chart."""
        api_key = self._get_api_key(__user__)
        username = self._get_username(__user__, user)
        if not username:
            return "Error: Last.fm username not provided."
        try:
            data = self._make_request(api_key, "user.getweeklytrackchart", {"user": username})
        except RuntimeError as exc:
            return f"Error: {exc}"
        if "weeklytrackchart" not in data or "track" not in data["weeklytrackchart"]:
            return "No weekly track chart data returned."
        tracks = data["weeklytrackchart"]["track"]
        if not tracks:
            return "No tracks found in this user's weekly chart."
        tracks = [tracks] if isinstance(tracks, dict) else tracks
        lines = [f"### Weekly Track Chart for {username}\n"]
        items = []
        for i, t in enumerate(tracks, 1):
            name = t.get("name", "Unknown")
            artist_val = t.get("artist", "Unknown")
            artist = (
                artist_val.get("name", "Unknown")
                if isinstance(artist_val, dict)
                else artist_val
            )
            playcount = t.get("playcount", "0")
            mbid = t.get("mbid", "N/A")
            url = t.get("url", "#")
            lines.append(f"{i}. **{name}** by *{artist}* ({playcount} plays) (MBID: {mbid}) – [{url}]({url})")
            items.append(
                {
                    "title": name,
                    "subtitle": artist,
                    "url": url,
                    "meta": [f"{self._fmt_num(playcount)} plays"],
                }
            )
        text = "\n".join(lines)
        if self._rich_enabled(__user__):
            body = self._render_list("Weekly track chart", f"{username}", items)
            return self._rich_response(body, text)
        return text