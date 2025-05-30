register_user_query = """ INSERT INTO user_ebay (unique_id, dev_id) VALUES (%s, %s) ON CONFLICT (dev_id) DO NOTHING ; """

