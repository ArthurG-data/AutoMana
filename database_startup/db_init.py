import glob, os
import aiohttp, asyncio
from table_population import populate_cards, populate_set
#from backend.database.get_database import get_connection




# download the files
template_url = (
    'https://api.scryfall.com/{ressource}'
)

urls =[
    template_url.format(ressource='bulk-data/default_cards'),
    template_url.format(ressource='bulk-data/oracle_cards'),
    template_url.format(ressource='bulk-data/unique_artwork')
]

async def get_download_url(url):
    """Fetch the actual download URI from the API response."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                info = await response.json()
                return info.get('download_uri')  # Returns None if missing
        except Exception as e:
            print(f"❌ Error fetching URL {url}: {e}")
            return None

async def download_data(url: str, destination_folder : str = 'files', chunk_size=10 * 1024) -> dict:
    """Download the file asynchronously from the given URL."""
    if not url:
        return {'error': 'Invalid download URL'}

    file_name = url.split('/')[-1]  # Extract file name from URL
    if ".json" not in file_name:
        file_name+=".json"
    destination_path = '/'.join([destination_folder, file_name])
    headers = {"Accept-Encoding": "gzip, deflate"}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as download_response:               
                with open(destination_path, "wb") as file:
                    while True:
                        chunk = await download_response.content.read(chunk_size)
                        if not chunk:
                            break  # Stop when no more data
                        file.write(chunk)
                          

            return {'message': f'File {file_name} downloaded successfully'}

        except Exception as e:
            return {'error': f'Error downloading {file_name}.json: {str(e)}'}
        
def execute_sql_files(folder_path, conn):

    """Executes all .sql files in a given folder in one transaction."""

    cursor = conn.cursor()

    try:
        # Get all .sql files in the folder
        sql_files = sorted(glob.glob(f"{folder_path}/*.sql"))  # Sort to maintain order

        
        print(f"📂 Found {len(sql_files)} SQL files. Executing...")
        
        for sql_file in sql_files:
            with open(sql_file, "r", encoding="utf-8") as file:
                sql_script = file.read()
                cursor.execute(sql_script)
                print(f"✅ Executed {sql_file}")

        conn.commit()  # Commit all scripts at once
        print("🎉 All SQL scripts executed successfully!")
    
    except Exception as e:
        conn.rollback()  # Rollback if any error occurs
        print(f"❌ Error executing SQL files: {e}")
    
    finally:
        cursor.close()
        conn.close()



async def main():
    """Runs the entire process: Fetch URLs, then download in parallel."""
    # 🔹 Step 1: Get all download URLs in parallel
    download_uris = await asyncio.gather(*(get_download_url(url) for url in urls))
    download_uris.append(template_url.format(ressource='sets'))
    # 🔹 Step 2: Start downloading all files in parallel
    results = await asyncio.gather(*(download_data(uri) for uri in download_uris if uri))
    print(results)
    #connection = get_connection()
    #execute_sql_files('database_startup/schemas', connection)
    #populate_set(connection)
    #populate_cards(connection)

# ✅ Run the async workflow
asyncio.run(main())




