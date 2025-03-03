from flask import Blueprint, request, jsonify
from flaskr.db import get_all_cards, get_all_sets, get_cards



cards_api_v1 = Blueprint(
    'cards_api_v1', __name__, url_prefix='/api/v1'
)

@cards_api_v1.route('/cards', methods=['GET'])
def cards():
    if request.method == 'GET':
        try:
            cards = get_all_cards()
            return jsonify(cards), 200
        except Exception as e:
            return jsonify(
                {'error':str(e)}), 500

@cards_api_v1.route('/sets', methods=['GET'])
def sets():
    if request.method == 'GET':
        try:
           
            sets = get_all_sets()
            return jsonify(sets), 200
        except Exception as e:
            return jsonify(
                {'error': str(e)}), 500
        
@cards_api_v1.route('/cards/', methods=['GET'])
def subset_sets():
    DEFAULT_CARDS_PER_PAGE = 20
    try:
        page= int(request.args.get('page',0))
    except(TypeError, ValueError) as e:
        print('Got bad value:\t', e)
        page = 0
    #determine the filters
    filters = {}
    return_filters = {}
    set_name = request.args.getlist('set_name')
    set_symbole = request.args.getlist('symb')
    released_data = request.args.get('released_at')
    name = request.args.get('name')
    search = request.args.get('text')
    if set_name:
        filters['set_name'] = set_name
        return_filters['set_name'] = set_name
    elif set_symbole:
        filters['symb'] = set_symbole
        return_filters['symb'] = set_symbole
    elif released_data:
        filters['released_date'] =released_data
        return_filters['released_date'] =released_data
    elif name:
        filters['name'] = name
        return_filters['name'] = name
    elif search:
        filters['text'] = search
        return_filters['search'] = search
    
    (cards, total_num_entries) = get_cards(
        filters, page, DEFAULT_CARDS_PER_PAGE
    )

    response = {
        'cards':cards,
        'page':page,
        'filter':return_filters,
        'entries_per_page':DEFAULT_CARDS_PER_PAGE,
        'total_results' : total_num_entries
    }
    return jsonify(response), 200
        


