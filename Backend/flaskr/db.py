
from flask import current_app, g
from werkzeug.local import LocalProxy
from flask_pymongo import PyMongo
from pymongo.mongo_client import MongoClient
from pymongo.errors import DuplicateKeyError, OperationFailure
from bson.objectid import ObjectId
from bson.errors import InvalidId
from pymongo.server_api import ServerApi


def get_db():

    db = getattr(g, "_database", None)
    uri = current_app.config['MONGO_URI']
    if db is None:
        print('Initiation connection')
        client = MongoClient(uri, server_api=ServerApi('1'))
        #db = g._database = PyMongo(current_app).db
        try:
            client.admin.command('ping')
            print("Pinged your deployment. You successfully connected to MongoDB!")
            g._database = client.get_database('card_info')
      
            db = g._database
        except Exception as e:
            print(e)
    return db

db = LocalProxy(get_db)

def close_db(e=None):
    db = g.pop('db', None)

    if db is not None:
        db.close()

def init_app(app):
    app.teardown_appcontext(close_db)


def get_all_cards():
    query = {}
    projection = {'_id':1, 'name' :1}
    try:
        card_list = db.unique_cards.find(query, projection)
        return [{str(card['_id']) : card['name']}for card in card_list]
    except Exception as e:
        print(f"Error retrieving cards: {e}")
        raise RuntimeError("Failed to retrieve cards from the database") from e
    
def get_cards_by_set(sets):
    '''
    find and return cards per set
    returns a list of dict, each dict containes a title and _id
    '''

    try:
        print(f'Fetching cards from sets: {sets}')

        pipeline = [
            {"$match": {"set": {"$in": sets}}},  # Filter only for specified sets
            {"$group": {
                "_id": "$set",  # Group by set name
                "cards": {
                    "$push": {
                        "id": {"$toString": "$_id"},  # Convert ObjectId to string
                        "name": "$name"
                    }
                }
            }}
        ]

        # Run aggregation
        result = db.unique_cards.aggregate(pipeline)
       
        # Convert to desired dictionary format
        sets_dict = {entry["_id"]: {card["id"]: card["name"] for card in entry["cards"]} for entry in result}

        return sets_dict
    except Exception as e:
        return e


def get_all_sets():
    '''
    return list of all sets in the database
    '''
    query = {'digital': False}
    projection = {'_id':1, 'code':1, 'name':1, 'released_at':1}
    try:
        sets_list =  list(db.sets.find(query, projection))
        print(sets_list)
        sets_dict = [{str(sets['_id']): {'code':sets['code'], 'name': sets['name'], 'released_at' : sets['released_at']}} for sets in sets_list]
        return sets_dict
    except Exception as e:
        print(f"Error retrieving sets: {e}")
        raise RuntimeError("Failed to retrieve sets from the database") from e
    

def make_list(data):
    if isinstance(data, str):
                data = [data]
    return data

def build_query_sort_project(filters):
    """
    Builds the `query` predicate, `sort` and `projection` attributes for a given
    filters dictionary.
    """
    query = {}
    project = {'_id': 0}
    sort = [("cmc", -1)]
    if filters:
        '''
        if "text" in filters:
            query = {"$text": {"$search": filters["text"]}}
            meta_score = {"$meta": "textScore"}
            sort = [("score", meta_score)]
            project = {"score": meta_score}'''
        if "set_name" in filters:
            set_names = make_list(filters["set_name"])
            query = {"set_name": {"$in": set_names}}
        elif 'symb' in filters:
            query = {'set': {'$in' : filters['symb']}}
        elif 'name' in filters:
            names = make_list(filters['name'])
            query = {'name': {'$in' : names}}
        elif 'released_at' in filters:
            query = {'released_at':{ '$gt' : datetime.strptime(filters["released_at"], "%Y-%m-%d")}}



          

    return query, sort, project

def get_cards(filters, page, cards_per_page):

    query, sort, project = build_query_sort_project(filters)
    try:
        if project:
            cursor = db.unique_cards.find(query, project).sort(sort)
        else:
            cursor = db.unique_cards.find(query).sort(sort)
        
        total_num_cards = 0
        if page == 0:
            total_num_cards = db.unique_cards.count_documents(query)
    
        cards = cursor.limit(cards_per_page)
        return (list(cards), total_num_cards)
    except Exception as e:
        raise RuntimeError('Error while filtering cards') from e
