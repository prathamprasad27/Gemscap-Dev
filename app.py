from flask import Flask, jsonify
from flask_cors import CORS
import sqlite3
import os

import populate_db_and_json
import helper
from flask import request

# Create Flask app and serve frontend from `frontend` directory
app = Flask(__name__, static_folder='frontend', static_url_path='')
CORS(app)

DB_PATH = 'positionmanager.db'


@app.route('/api/positions/<product>', methods=['GET'])
def api_positions(product):
    # Sanitize product input (alphanumeric only)
    if not product.isalnum():
        return jsonify({'error': 'Invalid product name'}), 400
        
    table_name = f"{product}_positions"
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Check if table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    if not cur.fetchone():
        # Table doesn't exist. We can either return empty or create it empty.
        # Let's create it effectively with 0 rows by just returning empty structure.
        conn.close()
        return jsonify({'contracts': [], 'rows': []})

    # Get table columns
    cur.execute(f"PRAGMA table_info('{table_name}')")
    cols = [r[1] for r in cur.fetchall()]

    # Read all rows into a dict by contract
    try:
        cur.execute(f"SELECT * FROM {table_name}")
        rows_db = cur.fetchall()
    except sqlite3.OperationalError:
        # Fallback if somehow table check passed but select failed
        conn.close()
        return jsonify({'contracts': [], 'rows': []})
        
    conn.close()

    # Build a map contract -> {col: value}
    contracts = []
    contract_map = {}
    for r in rows_db:
        # sqlite3 returns a tuple matching cols order
        contract = r[0]
        contract_map[contract] = {col: val for col, val in zip(cols, r)}
        contracts.append(contract)

    # Sort contracts chronologically using helper.contract_sort_key
    # Note: contract_sort_key uses parse_contract which handles prefixes or no prefixes
    contracts_sorted = sorted(contracts, key=lambda c: helper.contract_sort_key(c))

    # Build rows to return: Total, outright, then each structure column (excluding metadata)
    # Be careful: if there are no contracts, total_row is empty
    total_row = [contract_map[c].get('lots', 0) for c in contracts_sorted]
    outright_row = [contract_map[c].get('outright', 0) for c in contracts_sorted]

    # If outright column exists but contains only zeros (legacy state), show Total instead
    try:
        if sum(abs(int(x)) for x in outright_row) == 0:
            outright_row = total_row.copy()
    except Exception:
        # defensive: if values are None or non-int, fallback to totals
        outright_row = total_row.copy()

    rows = [
        {'name': 'Total', 'lots': total_row},
        {'name': 'outright', 'lots': outright_row}
    ]

    # Structure columns are any columns other than 'contract' and 'lots' and 'outright'
    meta = {'contract', 'lots', 'outright', 'positions_json', 'Total'}
    structure_cols = [c for c in cols if c not in meta]

    for s in structure_cols:
        s_row = [contract_map[c].get(s, 0) for c in contracts_sorted]
        rows.append({'name': s, 'lots': s_row})

    return jsonify({'contracts': contracts_sorted, 'rows': rows})


@app.route('/api/populate', methods=['POST', 'GET'])
def api_populate():
    # Get product from args (GET) or json (POST)
    product = 'CL'
    if request.method == 'POST':
        data = request.get_json()
        if data:
            product = data.get('product', 'CL')
    else:
        product = request.args.get('product', 'CL')

    # Recreate/populate DB and write JSON using the helper script
    populate_db_and_json.populate_db_and_write_json(product=product, db_path=DB_PATH, json_path=None)
    return jsonify({'status': 'ok', 'product': product})


@app.route('/', methods=['GET'])
def index():
    return app.send_static_file('index.html')


@app.route('/api/implement_hedge', methods=['POST'])
def api_implement_hedge():
    payload = request.get_json()
    product = payload.get('product')
    lis_structure_names = payload.get('lis_structure_names', [])
    lis_starting_contracts = payload.get('lis_starting_contracts', [])
    lis_num_lots = payload.get('lis_num_lots', [])

    try:
        base_contract, hedged_name, hedged_lots = helper.implement_hedge(
            product,
            lis_structure_names,
            lis_starting_contracts,
            lis_num_lots,
            db_path=DB_PATH
        )
    except Exception as e:
        msg = str(e)
        # If helper reported missing input structures, return them in a structured form
        if msg.startswith('MISSING_STRATEGIES:'):
            import json as _json
            missing = _json.loads(msg.split(':', 1)[1])
            return jsonify({'error': 'missing_strategies', 'missing': missing}), 400
        # If helper reported missing hedged pattern, forward payload so frontend can create it
        if msg.startswith('MISSING_HEDGED_PATTERN:'):
            import json as _json
            payload = _json.loads(msg.split(':', 1)[1])
            return jsonify({'error': 'missing_hedged_pattern', 'payload': payload}), 400
        return jsonify({'error': str(e)}), 400

    return jsonify({
        'base_contract': base_contract,
        'hedged_name': hedged_name,
        'hedged_lots': hedged_lots
    })


@app.route('/api/create_strategy', methods=['POST'])
def api_create_strategy():
    payload = request.get_json()
    name = payload.get('structure_name')
    pattern = payload.get('pattern')
    if not name or not isinstance(pattern, list):
        return jsonify({'error': 'invalid_payload'}), 400

    try:
        helper.create_custom_strategy_intraproduct(name, pattern, db_path=DB_PATH)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'status': 'ok', 'structure_name': name})


if __name__ == '__main__':
    # Run on all interfaces so you can open in browser at localhost
    app.run(host='0.0.0.0', port=5000, debug=True)
