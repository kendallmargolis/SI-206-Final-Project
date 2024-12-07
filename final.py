import spotipy
import sqlite3
import os
import json
from spotipy.oauth2 import SpotifyOAuth
import time
from requests.exceptions import ReadTimeout
import matplotlib.pyplot as plt  # For visualization

# Initialize Spotify client
def initialize_spotify_client(client_id, client_secret, redirect_uri):
    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope="playlist-read-private"
    )
    return spotipy.Spotify(auth_manager=auth_manager)

# Fetch playlist tracks
def fetch_playlist_tracks(sp, playlist_id, limit=25, offset=0):
    results = sp.playlist_items(
        playlist_id,
        fields='items(track(name, artists(name))), total',
        additional_types=['track'],
        limit=limit,
        offset=offset
    )
    tracks = []
    for item in results['items']:
        track = item['track']
        if track:
            tracks.append({
                'song_name': track['name'],
                'artists': [artist['name'] for artist in track['artists']]
            })
    return tracks, results.get('total', 0)

# Initialize database
def initialize_database():
    conn = sqlite3.connect('playlist_data.db', timeout=10)
    cur = conn.cursor()

    # Create Artists table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS Artists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            genres TEXT,
            popularity INTEGER
        )
    ''')

    # Create Songs table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS Songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            song_name TEXT UNIQUE,
            artist_id INTEGER,
            FOREIGN KEY (artist_id) REFERENCES Artists (id)
        )
    ''')
    conn.commit()
    return conn, cur

# Save artist to database
def save_artist_to_database(cur, artist_name, genres, popularity):
    genres_str = ', '.join(genres)
    cur.execute('''
        INSERT OR IGNORE INTO Artists (name, genres, popularity)
        VALUES (?, ?, ?)
    ''', (artist_name, genres_str, popularity))
    cur.execute('SELECT id FROM Artists WHERE name = ?', (artist_name,))
    return cur.fetchone()[0]

# Save song to database
def save_song_to_database(cur, song_name, artist_id):
    cur.execute('''
        INSERT OR IGNORE INTO Songs (song_name, artist_id)
        VALUES (?, ?)
    ''', (song_name, artist_id))

# Process and store playlist data
def process_and_store_playlist_data(sp, playlist_id, cur, conn, limit=25, offset=0):
    tracks, total = fetch_playlist_tracks(sp, playlist_id, limit=limit, offset=offset)

    if not tracks:
        print("No tracks fetched. Either the playlist is empty or you've reached the end.")
        return False, total

    for track in tracks:
        song_name = track['song_name']
        for artist_name in track['artists']:
            # Fetch artist details from Spotify API
            artist_data = sp.search(q=f"artist:{artist_name}", type="artist", limit=1)
            if artist_data['artists']['items']:
                artist_info = artist_data['artists']['items'][0]
                genres = artist_info.get('genres', [])
                popularity = artist_info.get('popularity', 0)
                # Save artist to database and retrieve artist_id
                artist_id = save_artist_to_database(cur, artist_name, genres, popularity)
                # Save song to database with artist_id
                save_song_to_database(cur, song_name, artist_id)

    conn.commit()
    return True, total
def process_data(cur):
    # Perform a join between Songs and Artists to calculate average popularity per artist
    query = '''
        SELECT Artists.name, AVG(Artists.popularity) as avg_popularity, COUNT(Songs.id) as song_count
        FROM Songs
        JOIN Artists ON Songs.artist_id = Artists.id
        GROUP BY Artists.name
        ORDER BY avg_popularity DESC
    '''
    cur.execute(query)
    results = cur.fetchall()

    # Display and return results
    print("Artist Name | Avg. Popularity | Number of Songs")
    for row in results:
        print(f"{row[0]} | {row[1]:.2f} | {row[2]}")

    return results

def write_to_file(data, filename="processed_data.txt"):
    # Write processed data to a text file
    with open(filename, "w") as file:
        file.write("Artist Name | Avg. Popularity | Number of Songs\n")
        file.write("-" * 50 + "\n")
        for row in data:
            file.write(f"{row[0]} | {row[1]:.2f} | {row[2]}\n")
    print(f"Processed data written to {filename}")

def main_process():
    conn, cur = initialize_database()  # Assuming this function initializes the DB and cursor
    data = process_data(cur)  # Perform the calculations and get the results
    write_to_file(data)  # Write results to a file
    conn.close()
def create_bar_chart(data):
    # Extract artist names and song counts
    artist_names = [row[0] for row in data]
    song_counts = [row[2] for row in data]

    # Create the bar chart
    plt.figure(figsize=(10, 6))
    plt.bar(artist_names, song_counts, color='skyblue', edgecolor='black')
    plt.title("Number of Songs Per Artist", fontsize=16)
    plt.xlabel("Artists", fontsize=12)
    plt.ylabel("Number of Songs", fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    # Save the visualization to a file
    plt.savefig("bar_chart_songs_per_artist.png")
    plt.show()
    print("Bar chart saved as 'bar_chart_songs_per_artist.png'")

# Visualization 2: Pie Chart
def create_pie_chart(data):
    # Extract artist names and song counts
    artist_names = [row[0] for row in data]
    song_counts = [row[2] for row in data]

    # Create the pie chart
    plt.figure(figsize=(8, 8))
    plt.pie(
        song_counts,
        labels=artist_names,
        autopct='%1.1f%%',
        startangle=140,
        colors=plt.cm.tab10.colors
    )
    plt.title("Proportion of Songs by Artist", fontsize=16)
    plt.tight_layout()

    # Save the visualization to a file
    plt.savefig("pie_chart_songs_per_artist.png")
    plt.show()
    print("Pie chart saved as 'pie_chart_songs_per_artist.png'")

def main_visualization():
    conn, cur = initialize_database()  # Assuming this function initializes the DB and cursor
    data = process_data(cur)  # Perform the calculations and get the results

    # Create visualizations
    create_bar_chart(data)
    create_pie_chart(data)

    conn.close()

# Main function
def main():
    CLIENT_ID = "7940031b89e5424cb3171a770da8d94f"
    CLIENT_SECRET = "b347685240ff41ee877577888d7c534f"
    REDIRECT_URI = "http://localhost:8080"

    sp = initialize_spotify_client(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI)
    conn, cur = initialize_database()

    playlist_id = "1yuH8vUahw61OKnxo3Ykym"
    limit = 25

    # Check or create a file to store the current offset
    offset_file = "offset.txt"
    if not os.path.exists(offset_file):
        with open(offset_file, "w") as f:
            f.write("0")

    # Read the current offset
    with open(offset_file, "r") as f:
        offset = int(f.read().strip())

    print(f"Fetching tracks {offset + 1} to {offset + limit} from the playlist...")
    success, total = process_and_store_playlist_data(sp, playlist_id, cur, conn, limit=limit, offset=offset)

    if success:
        offset += limit
        if offset >= total:
            print("All tracks have been processed and stored.")
            offset = 0  # Reset offset when all tracks are processed
        else:
            print(f"Fetched and stored {min(offset, total)} of {total} total tracks.")

    # Save the new offset
    with open(offset_file, "w") as f:
        f.write(str(offset))

    conn.close()

if __name__ == "__main__":
    #main()
    #main_process()
   main_visualization()