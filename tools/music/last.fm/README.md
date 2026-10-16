# Last.fm Tool for Open WebUI

This tool integrates with the Last.fm API to allow users to discover music, fetch play history, and get information about artists, albums, and tracks within the Open WebUI interface.

## Features

- Get recent tracks played by a user
- Get user information and play counts
- Search for artists, albums, and tracks
- Get detailed information about artists, albums, and tracks
- Get top artists, albums, and tracks for a user
- Get similar artists and tracks

## Setup Instructions

### 1. Obtain a Last.fm API Key

To use this tool, you need to obtain an API key from Last.fm:

1. Go to [https://www.last.fm/api/account/create](https://www.last.fm/api/account/create)
2. Log in with your Last.fm account (or create one if you don't have one)
3. Fill out the application form:
   - Application name: You can use something like "Open WebUI Last.fm Tool"
   - Application description: Describe how you'll use the API
   - Application website: Your website or leave blank if not applicable
4. Agree to the terms and submit the form
5. You will receive an API key (a long string of letters and numbers)

### 2. Configure the Tool in Open WebUI

1. Open Open WebUI and navigate to the Tools section
2. Find the "Last.fm" tool in the list
3. Click on the tool to configure it
4. Enter your Last.fm API key in the "Last.fm API Key" field
5. Enter your Last.fm username in the "Last.fm API User" field
6. Save the configuration

## Available Functions

Once configured, the tool provides the following functions:

### User Functions
- `get_recent_tracks`: Get the user's recently played tracks
- `get_user_info`: Get information about the user
- `get_user_top_artists`: Get the user's top artists
- `get_user_top_albums`: Get the user's top albums
- `get_user_top_tracks`: Get the user's top tracks
- `get_user_weekly_artist_chart`: Get the user's weekly artist chart
- `get_user_weekly_album_chart`: Get the user's weekly album chart
- `get_user_weekly_track_chart`: Get the user's weekly track chart

### Artist Functions
- `get_artist_info`: Get information about an artist
- `get_artist_top_albums`: Get an artist's top albums
- `get_artist_top_tracks`: Get an artist's top tracks
- `get_artist_similar`: Get artists similar to a given artist

### Album Functions
- `get_album_info`: Get information about an album
- `get_album_top_tracks`: Get an album's top tracks

### Track Functions
- `get_track_info`: Get information about a track
- `get_track_similar`: Get tracks similar to a given track

### Search Functions
- `search_artist`: Search for artists
- `search_album`: Search for albums
- `search_track`: Search for tracks

## Usage Examples

After configuring the tool, you can use it in your Open WebUI chats by calling the functions. For example:

```
Which five songs did I recently listen to?
What are my top albums?
Display my last.fm user profile.
Search for The Talking Heads.
Fetch information about Radiohead.
```

## Notes

- The tool requires both an API key and a username to function properly
- Last.fm API has rate limits; please use the tool responsibly
- Some functions may return limited data if the user has limited scrobbling history
- All data is fetched in real-time from the Last.fm API

## Troubleshooting

If you encounter issues:

1. Verify your API key is correct and active
2. Verify your Last.fm username is correct
3. Check that you have scrobbling history in your Last.fm account
4. Ensure you have internet connectivity to reach the Last.fm API
5. Check the Open WebUI logs for any error messages

For more information about the Last.fm API, visit: [https://www.last.fm/api](https://www.last.fm/api)