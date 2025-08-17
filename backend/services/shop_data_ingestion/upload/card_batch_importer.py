from backend.database.get_database import get_connection
from backend.modules.internal.cards import models, services
import ijson

def process_large_cards_json(file_path: str, ):
    print(f"Processing {file_path}...")
    db_conn_gen = get_connection()
    conn = next(db_conn_gen)
    cursor = conn.cursor()

    with open(file_path, "rb") as f:
        # Use ijson to stream the array of cards
        cards_iter = ijson.items(f, "item")

        batch = []
        batch_size = 100 # Tune batch size here

        for card_json in cards_iter:
            try:
                card = models.CreateCard(**card_json)
                batch.append(card)

                if len(batch) >= batch_size:
                    services.insert_card_batch(conn, cursor, models.CreateCards(items = batch))
                    batch = [] 

            except Exception as e:
                conn.rollback()
                batch = [] 
                print(f"Error parsing card: {e}")

        # Insert any remaining cards
        if batch:
            services.insert_card_batch(conn, cursor, models.CreateCards(items = batch))

    conn.close()
    print("Processing complete.")

