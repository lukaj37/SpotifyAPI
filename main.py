import os
from functools import wraps
from flask import Flask, redirect, request, jsonify, session, url_for, g
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import FlaskSessionCacheHandler

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(64)

# Spotify API configuration
CLIENT_ID = '4998ad91a94744c7911f5c9900b9089f'
CLIENT_SECRET = '71e35f3abba549bf95f946f2d7fd0ec1'
REDIRECT_URI = 'http://localhost:5000/callback'
SCOPE = 'user-read-private user-read-email playlist-read-private playlist-modify-private playlist-modify-public'

# Cache handler using Flask session
cache_handler = FlaskSessionCacheHandler(session)

# Factory to create new SpotifyOAuth instances
def create_spotify_oauth():
    return SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        cache_handler=cache_handler,
        show_dialog=True
    )

# Custom decorator to require a valid Spotify token
def require_spotify_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        sp_oauth = create_spotify_oauth()
        token_info = sp_oauth.get_cached_token()

        if not sp_oauth.validate_token(token_info):
            return redirect(sp_oauth.get_authorize_url())

        # Store Spotify client in Flask's global context
        g.spotify = Spotify(auth=token_info['access_token'])
        return f(*args, **kwargs)

    return decorated_function

# Home route - checks token or redirects to auth
@app.route('/')
def home():
    sp_oauth = create_spotify_oauth()
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)
    return redirect(url_for('get_playlists'))

# Callback route - handles redirect from Spotify and stores token
@app.route('/callback')
def callback():
    sp_oauth = create_spotify_oauth()
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code=code)
    return redirect(url_for('get_playlists'))

# Protected route - returns user's playlists
@app.route('/get_playlists')
@require_spotify_token
def get_playlists():
    sp = g.spotify
    playlists = sp.current_user_playlists()
    playlists_info = [
        {'name': pl['name'], 'url': pl['external_urls']['spotify']}
        for pl in playlists['items']
    ]
    return jsonify(playlists_info)

@app.route('/create_playlist', methods=['POST'])
@require_spotify_token
def create_playlist():
    sp = g.spotify
    data = request.get_json()
    playlist_name = data.get('name')

    if not playlist_name:
        return jsonify({'error': 'Playlist name is required'}), 400

    user_id = sp.current_user()['id']
    playlist = sp.user_playlist_create(user=user_id, name=playlist_name, public=False)

    return jsonify({
        'id': playlist['id'],
        'name': playlist['name'],
        'url': playlist['external_urls']['spotify']
    })

@app.route('/search_song', methods=['GET'])
@require_spotify_token
def search_song():
    sp = g.spotify
    query = request.args.get('name')

    if not query:
        return jsonify({'error': 'Query parameter "name" is required'}), 400

    results = sp.search(q=query, type='track', limit=10)
    tracks = results.get('tracks', {}).get('items', [])

    songs = [{
        'id': track['id'],
        'name': track['name'],
        'artists': [artist['name'] for artist in track['artists']],
        'url': track['external_urls']['spotify']
    } for track in tracks]

    return jsonify(songs)

@app.route('/add_song_to_playlist', methods=['POST'])
@require_spotify_token
def add_song_to_playlist():
    sp = g.spotify
    data = request.get_json()

    playlist_id = data.get('playlist_id')
    track_id = data.get('track_id')

    if not playlist_id or not track_id:
        return jsonify({'error': 'playlist_id and track_id are required'}), 400

    sp.playlist_add_items(playlist_id, [track_id])
    return jsonify({'message': f'Track {track_id} added to playlist {playlist_id}'})

# Logout route - clears the session
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# Run the app
if __name__ == '__main__':
    app.run(debug=True)
