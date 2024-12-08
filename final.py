import requests
import sqlite3
import os
import matplotlib.pyplot as plt
import random

def initialize_database():
    conn = sqlite3.connect('ticketmaster_data.db', timeout=10)
    cur = conn.cursor()

    # Create Artists table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS Artists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            genre TEXT,
            min_price REAL,
            max_price REAL
        )
    ''')

    # Create Events table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS Events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT UNIQUE,
            artist_id INTEGER,
            city TEXT,
            state TEXT,
            FOREIGN KEY (artist_id) REFERENCES Artists (id)
        )
    ''')
    conn.commit()
    return conn, cur

def save_artist_to_database(cur, artist_name, genre, min_price, max_price):
    cur.execute('''
        INSERT OR IGNORE INTO Artists (name, genre, min_price, max_price)
        VALUES (?, ?, ?, ?)
    ''', (artist_name, genre, min_price, max_price))
    cur.execute('SELECT id FROM Artists WHERE name = ?', (artist_name,))
    return cur.fetchone()[0]

def fetch_and_store_data_by_genre(genre):
    # Ticketmaster API details
    api_key = 'mrmAhtFJt4HOkuOmsz9vtU1nMkB1TX3X'
    url = 'https://app.ticketmaster.com/discovery/v2/events.json'
    params = {
        'apikey': api_key,
        'keyword': genre,
        'countryCode': 'US',
        'startDateTime': '2024-12-01T00:00:00Z',
        'endDateTime': '2024-12-31T23:59:59Z',
        'size': 25,
        'page': 0
    }

    conn, cur = initialize_database()
    page_file = f"current_page_{genre}.txt"

    if not os.path.exists(page_file):
        with open(page_file, "w") as f:
            f.write("0")
    with open(page_file, "r") as f:
        current_page = int(f.read().strip())

    print(f"Fetching events for genre '{genre}', page {current_page + 1}...")
    params['page'] = current_page
    response = requests.get(url, params=params)

    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        return

    data = response.json()
    events = data.get('_embedded', {}).get('events', [])

    if not events:
        print("No more events to process.")
        return

    print(f"Number of events fetched: {len(events)}")
    for event in events:
        price_info = event.get('priceRanges', [{}])[0]
        min_price = price_info.get('min', None)
        max_price = price_info.get('max', None)

        # Skip events with no price information
        if min_price is None or max_price is None:
            print(f"Skipping event {event.get('name', 'Unknown')} due to missing price data.")
            continue

        # Save artist and get artist ID
        artist_name = event.get('_embedded', {}).get('attractions', [{}])[0].get('name', 'Unknown')
        artist_id = save_artist_to_database(cur, artist_name, genre, min_price, max_price)

        # Save event
        venue = event.get('_embedded', {}).get('venues', [{}])[0]
        city = venue.get('city', {}).get('name', 'Unknown')
        state = venue.get('state', {}).get('stateCode', 'Unknown')
        save_event_to_database(cur, event.get('name', 'Unknown'), artist_id, city, state)
        
    # Commit and update page
    conn.commit()
    current_page += 1
    with open(page_file, "w") as f:
        f.write(str(current_page))
    conn.close()
    print(f"Data from page {current_page} for genre '{genre}' stored successfully!")

def save_event_to_database(cur, event_name, artist_id, city, state):
    cur.execute('''
        INSERT OR IGNORE INTO Events (event_name, artist_id, city, state)
        VALUES (?, ?, ?, ?)
    ''', (event_name, artist_id, city, state))

def analyze_genre_prices():
    try:
        conn = sqlite3.connect('ticketmaster_data.db', timeout=10)
        cur = conn.cursor()

        # Query: Average ticket price by genre
        cur.execute('''
            SELECT genre, AVG((min_price + max_price) / 2.0) AS avg_price
            FROM Artists
            WHERE min_price IS NOT NULL AND max_price IS NOT NULL AND min_price > 0 AND max_price > 0
            GROUP BY genre
        ''')
        genre_prices = cur.fetchall()

        # Query: Distribution of events by price range and city
        cur.execute('''
            SELECT Events.city, 
                   CASE 
                       WHEN Artists.min_price < 50 THEN 'Low'
                       WHEN Artists.min_price BETWEEN 50 AND 100 THEN 'Medium'
                       ELSE 'High'
                   END AS price_range,
                   COUNT(Events.id) AS event_count
            FROM Events
            JOIN Artists ON Events.artist_id = Artists.id
            WHERE Events.city IS NOT NULL AND Artists.min_price IS NOT NULL
            GROUP BY Events.city, price_range
        ''')
        distribution_data = cur.fetchall()
        
        # Write average ticket prices by genre to a file
        if genre_prices:
            with open('average_ticket_prices.txt', 'w') as file:
                file.write("Average Ticket Prices by Genre:\n")
                for genre, avg_price in genre_prices:
                    file.write(f"{genre}: ${avg_price:.2f}\n")
            print("Average ticket prices written to 'average_ticket_prices.txt'.")

        # Write distribution of events by city and price range to a file
        if distribution_data:
            with open('event_distribution.txt', 'w') as file:
                file.write("Event Distribution by City and Price Range:\n")
                for city, price_range, event_count in distribution_data:
                    file.write(f"{city} ({price_range}): {event_count} events\n")
            print("Event distribution data written to 'event_distribution.txt'.")

        # Visualization 1: Bar Chart - Average Ticket Price by Genre
        if genre_prices:
            genres = [row[0] for row in genre_prices]
            avg_prices = [row[1] for row in genre_prices]
            colors = [f'#{random.randint(0, 0xFFFFFF):06x}' for _ in genres]
            plt.figure(figsize=(10, 6))
            plt.bar(genres, avg_prices, color=colors)
            plt.title('Average Ticket Price by Genre')
            plt.xlabel('Genre')
            plt.ylabel('Average Price (USD)')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            plt.savefig('genre_price_bar_chart.png')
            plt.show()

        # Visualization 2: Stack Plot - Events Across Prices and Cities
        if distribution_data:
            cities = list(sorted(set(row[0] for row in distribution_data)))
            price_ranges = ['Low', 'Medium', 'High']  # Fixed price ranges

            # Create a dictionary to store event counts for each price range
            event_counts = {price_range: [0] * len(cities) for price_range in price_ranges}
            city_to_idx = {city: i for i, city in enumerate(cities)}

            # Populate event counts
            for city, price_range, event_count in distribution_data:
                if price_range in event_counts:
                    event_counts[price_range][city_to_idx[city]] = event_count

            # Prepare data for stack plot
            low_counts = event_counts['Low']
            medium_counts = event_counts['Medium']
            high_counts = event_counts['High']

            # Create the stack plot
            plt.figure(figsize=(12, 8))
            plt.stackplot(
                cities,
                low_counts,
                medium_counts,
                high_counts,
                labels=price_ranges,
                colors=['#88CCEE', '#DDCC77', '#CC6677']
            )
            plt.title('Distribution of Events Across Prices and Cities')
            plt.xlabel('City')
            plt.ylabel('Event Count')
            plt.legend(title='Price Range')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()

            # Save and show the plot
            plt.savefig('price_city_distribution_stackplot.png')
            plt.show()

        else:
            print("No data available for price and city distribution.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()



if __name__ == "__main__":
    genre = input("Enter the genre you want to search events for (e.g., Pop, Rock): ").strip()

    if not genre:
        print("Invalid input. Please enter a valid genre.")
 
    else:
        # Debugging: Confirm inputs
        print(f"Fetching data for genre: {genre}")
       

        # Fetch and store data for the specified genre
        fetch_and_store_data_by_genre(genre)

        # Analyze and visualize results for both genre and city
        analyze_genre_prices()
