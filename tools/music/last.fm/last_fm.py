"""
title: last.fm
description: Discover music and fetch last.fm play history data.
author: mattserrano
version: 0.1.0
"""

import os
import requests
from pydantic import BaseModel, Field
from typing import Annotated, Optional


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
            type="string",
        )

    def _make_request(self, api_key: str, method: str, params: dict) -> Optional[dict]:
        """Internal helper to call Last.fm API."""
        if not api_key:
            return None
        url = "http://ws.audioscrobbler.com/2.0/"
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
            return resp.json()
        except requests.RequestException as e:
            # Return error info in a dict for the caller to handle
            return {"error": str(e)}

    # album methods
    def get_album_info(
        self,
        __user__: dict,
        artist: Annotated[str, Field(description="Artist name")],
        album: Annotated[str, Field(description="Album name")],
        mbid: Annotated[
            str | None,
            Field(
                description="MusicBrainz ID for the album. If provided, artist and album are ignored."
            ),
        ] = None,
    ) -> str:
        """Return information about a specific album."""
        api_key = __user__["valves"].last_fm_api_key
        if not api_key:
            return "Error: Last.fm API key not provided."
        params = {}
        if mbid:
            params["mbid"] = mbid
        else:
            params["artist"] = artist
            params["album"] = album
        data = self._make_request(api_key, "album.getInfo", params)
        if not data:
            return "No album information found. Please check the artist and album names, or provide a valid MBID."
        if "error" in data:
            return f"API error: {data['error']}"
        if "album" not in data:
            return "No album data returned."
        album_data = data["album"]
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
        return "\n".join(lines)

    def album_search(
        self,
        __user__: dict,
        artist: Annotated[str, Field(description="Artist name")],
        album: Annotated[str, Field(description="Album name")],
    ) -> str:
        """Search for an album and return its information."""
        api_key = __user__["valves"].last_fm_api_key
        if not api_key:
            return "Error: Last.fm API key not provided."
        params = {"album": album, "artist": artist}
        data = self._make_request(api_key, "album.getInfo", params)
        if not data:
            return "No album information found. Please check the artist and album names, or provide a valid MBID."
        if "error" in data:
            return f"API error: {data['error']}"
        if "album" not in data:
            return "No album data returned."
        album_data = data["album"]
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
        return "\n".join(lines)

    # artist methods
    def get_artist_similar(
        self,
        __user__: dict,
        artist: Annotated[str, Field(description="Artist name")],
        mbid: Annotated[
            str | None,
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
    ) -> str:
        """Return similar artists to a given artist."""
        api_key = __user__["valves"].last_fm_api_key
        if not api_key:
            return "Error: Last.fm API key not provided."
        params = {}
        if mbid:
            params["mbid"] = mbid
        else:
            params["artist"] = artist
        params["limit"] = limit
        data = self._make_request(api_key, "artist.getSimilar", params)
        if not data:
            return "No similar artists found. Please check the artist name, or provide a valid MBID."
        if "error" in data:
            return f"API error: {data['error']}"
        if "similarartists" not in data or "artist" not in data["similarartists"]:
            return "No similar artists data returned."
        similar_artists = data["similarartists"]["artist"]
        if not similar_artists:
            return "No similar artists found."
        # Ensure it's a list (API returns dict for single item?)
        if isinstance(similar_artists, dict):
            similar_artists = [similar_artists]
        lines = [f"### Similar Artists to {artist}\n"]
        for i, sim_artist in enumerate(similar_artists, 1):
            name = sim_artist.get("name", "Unknown")
            mbid_val = sim_artist.get("mbid", "N/A")
            match = sim_artist.get("match", "0")  # similarity score
            url = sim_artist.get("url", "#")
            lines.append(
                f"{i}. **{name}** (MBID: {mbid_val}, match score: {match}) – [{url}]({url})"
            )
        return "\n".join(lines)

    def artist_search(
        self,
        __user__: dict,
        artist: Annotated[str, Field(description="Artist name")],
    ) -> str:
        """Search for an artist and return its information."""
        api_key = __user__["valves"].last_fm_api_key
        if not api_key:
            return "Error: Last.fm API key not provided."
        params = {"artist": artist}
        data = self._make_request(api_key, "artist.getInfo", params)
        if not data:
            return "No artist information found. Please check the artist name, or provide a valid MBID."
        if "error" in data:
            return f"API error: {data['error']}"
        if "artist" not in data:
            return "No artist data returned."
        artist_data = data["artist"]
        name = artist_data.get("name", "Unknown")
        mbid_val = artist_data.get("mbid", "N/A")
        url = artist_data.get("url", "#")
        listeners = artist_data.get("stats", {}).get("listeners", "0")
        playcount = artist_data.get("stats", {}).get("playcount", "0")
        # Extract wiki summary if available
        wiki_summary = ""
        if "bio" in artist_data and artist_data["bio"]:
            wiki_summary = artist_data["bio"].get("summary", "")
            # Truncate summary to first 500 characters for brevity
            if len(wiki_summary) > 500:
                wiki_summary = wiki_summary[:500] + "..."
        lines = [
            f"### Artist Info: {name}",
            f"- **MBID:** {mbid_val}",
            f"- **URL:** [{url}]({url})",
            f"- **Listeners:** {listeners}",
            f"- **Playcount:** {playcount}",
        ]
        if wiki_summary:
            lines.append(f"- **Summary:** {wiki_summary}")
        return "\n".join(lines)

    # track methods
    def get_track_info(
        self,
        __user__: dict,
        artist: Annotated[str, Field(description="Artist name")],
        track: Annotated[str, Field(description="Track name")],
        mbid: Annotated[
            str | None,
            Field(
                description="MusicBrainz ID for the track. If provided, artist and track are ignored."
            ),
        ] = None,
    ) -> str:
        """Return information about a specific track."""
        api_key = __user__["valves"].last_fm_api_key
        if not api_key:
            return "Error: Last.fm API key not provided."
        params = {}
        if mbid:
            params["mbid"] = mbid
        else:
            params["artist"] = artist
            params["track"] = track
        data = self._make_request(api_key, "track.getInfo", params)
        if not data:
            return "No track information found. Please check the artist and track names, or provide a valid MBID."
        if "error" in data:
            return f"API error: {data['error']}"
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
            duration_seconds = int(duration_str) // 1000 if duration_str.isdigit() else "N/A"
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
        return "\n".join(lines)

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
            str | None,
            Field(
                description="MusicBrainz ID for the track. If provided, artist and track are ignored."
            ),
        ] = None,
    ) -> str:
        """Return similar tracks to a given track."""
        api_key = __user__["valves"].last_fm_api_key
        if not api_key:
            return "Error: Last.fm API key not provided."
        params = {}
        if mbid:
            params["mbid"] = mbid
        else:
            params["artist"] = artist
            params["track"] = track
        params["limit"] = limit
        data = self._make_request(api_key, "track.getSimilar", params)
        if not data:
            return "No similar tracks found. Please check the artist and track names, or provide a valid MBID."
        if "error" in data:
            return f"API error: {data['error']}"
        if "similartracks" not in data or "track" not in data["similartracks"]:
            return "No similar tracks data returned."
        similar_tracks = data["similartracks"]["track"]
        if not similar_tracks:
            return "No similar tracks found."
        # Ensure it's a list
        if isinstance(similar_tracks, dict):
            similar_tracks = [similar_tracks]
        lines = [f"### Similar Tracks to {track} by {artist}\n"]
        for i, sim_track in enumerate(similar_tracks, 1):
            name = sim_track.get("name", "Unknown")
            artist_name = sim_track.get("artist", {}).get("name", "Unknown")
            match = sim_track.get("match", "0")
            lines.append(f"{i}. {name} – {artist_name} (match: {match})")
        return "\n".join(lines)

    def track_search(
        self,
        __user__: dict,
        track: Annotated[str, Field(description="Track name")],
        artist: Annotated[str, Field(description="Artist name")],
    ) -> str:
        """Search for a track and return its information."""
        api_key = __user__["valves"].last_fm_api_key
        if not api_key:
            return "Error: Last.fm API key not provided."

        params = {"track": track, "artist": artist}
        data = self._make_request(api_key, "track.getInfo", params)
        if not data:
            return "No track information found. Please check the artist and track names, or provide a valid MBID."
        if "error" in data:
            return f"API error: {data['error']}"
        if "track" not in data:
            return "No track data returned."
        track_data = data["track"]
        name = track_data.get("name", "Unknown")
        artist_name = track_data.get("artist", {}).get("name", "Unknown")
        mbid_val = track_data.get("mbid", "N/A")
        url = track_data.get("url", "#")
        duration = track_data.get("duration", "0")  # in milliseconds
        listeners = track_data.get("listeners", "0")
        playcount = track_data.get("playcount", "0")
        # Extract wiki summary if available
        wiki_summary = ""
        if "wiki" in track_data and track_data["wiki"]:
            wiki_summary = track_data["wiki"].get("summary", "")
            if len(wiki_summary) > 500:
                wiki_summary = wiki_summary[:500] + "..."
        lines = [
            f"### Track Info: {name} by {artist_name}",
            f"- **MBID:** {mbid_val}",
            f"- **URL:** [{url}]({url})",
            f"- **Duration:** {int(duration)//1000 if duration.isdigit() else 'N/A'} seconds",
            f"- **Listeners:** {listeners}",
            f"- **Playcount:** {playcount}",
        ]
        if wiki_summary:
            lines.append(f"- **Summary:** {wiki_summary}")
        return "\n".join(lines)

    # user methods
    def get_user_info(
        self,
        __user__: dict,
        user: Annotated[
            str | None,
            Field(
                description="Last.fm username. If not provided, the default user from the valves will be used."
            ),
        ] = None,
    ) -> str:
        """Return information about a specific user."""
        api_key = __user__["valves"].last_fm_api_key
        username = user or __user__["valves"].last_fm_api_user
        if not api_key:
            return "Error: Last.fm API key not provided."

        data = self._make_request(api_key, "user.getInfo", {"user": username})
        if not data:
            return "Error: Last.fm API key not provided."
        if "error" in data:
            return f"API error: {data['error']}"
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
        bootstrap = user_data.get("bootstrap", "0")
        registered = user_data.get("registered", {}).get("#text", "N/A")
        url = user_data.get("url", "#")
        image_url = ""
        if "image" in user_data and isinstance(user_data["image"], list):
            # Find medium or large image
            for img in user_data["image"]:
                if img.get("size") == "medium":
                    image_url = img.get("#text", "")
                    break
            if not image_url and user_data["image"]:
                image_url = user_data["image"][0].get("#text", "")
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
        return "\n".join(lines)

    def get_user_similar(
        self,
        __user__: dict,
        limit: Annotated[
            int,
            Field(
                default=5,
                description="Number of similar users to return (1-10).",
                ge=1,
                le=10,
            ),
        ],
        user: Annotated[
            str | None,
            Field(
                description="Last.fm username. If not provided, the default user from the valves will be used."
            ),
        ] = None,
    ) -> str:
        """Return similar users to a given user."""
        api_key = __user__["valves"].last_fm_api_key
        if not api_key:
            return "Error: Last.fm API key not provided."
        username = user or __user__["valves"].last_fm_api_user
        if not username:
            return "Error: Last.fm username not provided."
        params = {"user": username, "limit": limit}
        data = self._make_request(api_key, "user.getSimilar", params)
        if not data:
            return "No similar users found. Please provide a valid username."
        if "error" in data:
            return f"API error: {data['error']}"
        if "similarusers" not in data or "user" not in data["similarusers"]:
            return "No similar users data returned."
        similar_users = data["similarusers"]["user"]
        if not similar_users:
            return "No similar users found."
        # Ensure it's a list
        if isinstance(similar_users, dict):
            similar_users = [similar_users]
        lines = [f"### Similar Users to {username}\n"]
        for i, sim_user in enumerate(similar_users, 1):
            name = sim_user.get("name", "Unknown")
            match = sim_user.get("match", "0")
            image_url = ""
            if "image" in sim_user and isinstance(sim_user["image"], list):
                for img in sim_user["image"]:
                    if img.get("size") == "medium":
                        image_url = img.get("#text", "")
                        break
                if not image_url and sim_user["image"]:
                    image_url = sim_user["image"][0].get("#text", "")
            user_info = f"{i}. {name} (match: {match})"
            if image_url:
                user_info += f" ![Avatar]({image_url})"
            lines.append(user_info)
        return "\n".join(lines)

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
    ) -> str:
        """Return list of the user's top albums."""
        api_key = __user__["valves"].last_fm_api_key
        if not api_key:
            return "Error: Last.fm API key not provided."
        username = __user__["valves"].last_fm_api_user
        if not username:
            return "Error: Last.fm username not provided."
        data = self._make_request(
            api_key, "user.gettopalbums", {"user": username, "limit": limit}
        )
        if not data:
            return "No top albums found."
        if "error" in data:
            return f"API error: {data['error']}"
        if "topalbums" not in data or "album" not in data["topalbums"]:
            return "No album data returned."
        albums = data["topalbums"]["album"]
        if not albums:
            return "No albums found for this user."
        lines = [f"### Top {len(albums)} Albums for {username}\n"]
        for i, album in enumerate(albums, 1):
            name = album.get("name", "Unknown")
            artist = album.get("artist", {}).get("name", "Unknown")
            playcount = album.get("playcount", "0")
            lines.append(f"{i}. **{name}** by *{artist}* ({playcount} plays)")
        return "\n".join(lines)

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
    ) -> str:
        """Return a formatted list of the user's top (most listened to) tracks."""
        username = __user__["valves"].last_fm_api_user
        api_key = __user__["valves"].last_fm_api_key
        if not username:
            return "Error: Last.fm username not provided."
        data = self._make_request(
            api_key, "user.gettoptracks", {"user": username, "limit": limit}
        )
        if not data:
            return "No top tracks found."
        if "error" in data:
            return f"API error: {data['error']}"
        if "toptracks" not in data or "track" not in data["toptracks"]:
            return "No track data returned."
        tracks = data["toptracks"]["track"]
        if not tracks:
            return "No tracks found for this user."
        lines = [f"### Top {len(tracks)} Tracks for {username} (Playlist)\n"]
        for i, track in enumerate(tracks, 1):
            name = track.get("name", "Unknown")
            artist = track.get("artist", {}).get("name", "Unknown")
            playcount = track.get("playcount", "0")
            lines.append(f"{i}. {name} – {artist} ({playcount} plays)")
        return "\n".join(lines)