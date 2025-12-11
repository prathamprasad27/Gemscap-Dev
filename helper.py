"""Helper functions extracted from the notebook `position_manager_initial.ipynb`.

This module provides utilities for contract month ordering, contract expansion,
and simple DB-backed custom strategy storage and lookup.
"""
import math
import sqlite3
import json
import ast
from typing import List, Tuple, Optional

# Month codes and lookup used across the project
lis_months: List[str] = ["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"]
month_to_index = {m: i for i, m in enumerate(lis_months)}


# ----- Contract parsing helpers (robust to prefixes like 'CLF25') -----
def parse_contract(contract: str) -> Tuple[Optional[str], str, int]:
    """
    Parse a contract code and return (prefix, month_letter, year_int).
    Examples:
      'H25'   -> (None, 'H', 25)
      'CLF25' -> ('CL', 'F', 25)
    """
    # find first digit (start of year)
    first_digit_idx = None
    for i, ch in enumerate(contract):
        if ch.isdigit():
            first_digit_idx = i
            break
    if first_digit_idx is None or first_digit_idx == 0:
        raise ValueError(f"Can't parse contract '{contract}'")

    # month letter is the char immediately before first_digit_idx
    month_letter = contract[first_digit_idx - 1]
    prefix = contract[: first_digit_idx - 1] or None
    year_part = contract[first_digit_idx:]
    try:
        year_int = int(year_part)
    except ValueError:
        raise ValueError(f"Can't parse year from contract '{contract}'")

    if month_letter not in month_to_index:
        raise ValueError(f"Unknown month code '{month_letter}' in contract '{contract}'")

    return prefix, month_letter, year_int


def compose_contract(prefix: Optional[str], month_letter: str, year_int: int) -> str:
    """Re-compose a contract preserving an optional prefix."""
    if prefix:
        return f"{prefix}{month_letter}{year_int}"
    return f"{month_letter}{year_int}"


# ---- Core utilities ----
def expand_contracts_and_lots(contracts: List[str], lots: List[int]) -> Tuple[List[str], List[int]]:
    """Expand a sparse list of contracts and lots into a continuous month-by-month
    list between the first and last contract (inclusive).

    Example: contracts=['H25','K25'], lots=[1,2] -> ['H25','J25','K25'], [1,0,2]
    Accepts contracts with optional prefix like 'CLF25'.
    """
    if len(contracts) != len(lots):
        raise ValueError("contracts and lots must have same length")

    # ---- Parse contracts into (prefix, month_index, year) ----
    parsed = []
    for c in contracts:
        prefix, month_letter, year = parse_contract(c)
        parsed.append((prefix, month_to_index[month_letter], year))

    # ---- Determine the start and end points ----
    start_prefix, start_month, start_year = parsed[0]
    end_prefix, end_month, end_year = parsed[-1]

    # prefixes must match for a sensible contiguous expansion
    if start_prefix != end_prefix:
        # we allow None vs None, but otherwise warn / fail
        if not (start_prefix is None and end_prefix is None):
            raise ValueError("Cannot expand contracts with different prefixes: "
                             f"'{contracts[0]}' vs '{contracts[-1]}'")

    prefix = start_prefix

    # ---- Expand continuously month-by-month ----
    expanded_contracts = []
    expanded_lots = []

    lot_map = {contracts[i]: lots[i] for i in range(len(contracts))}

    ym = start_month
    yy = start_year

    while True:
        contract_code = compose_contract(prefix, lis_months[ym], yy)
        expanded_contracts.append(contract_code)
        expanded_lots.append(lot_map.get(contract_code, 0))

        if yy == end_year and ym == end_month:
            break

        ym += 1
        if ym == 12:
            ym = 0
            yy += 1

    return expanded_contracts, expanded_lots


def next_contract(contract: str, step: int) -> str:
    """Return the contract code that is `step` months after `contract`.

    Example: next_contract('CLH25', 1) -> 'CLJ25' (prefix preserved)
    """
    prefix, month_letter, year = parse_contract(contract)
    idx = month_to_index[month_letter]
    new_idx = idx + step
    year += new_idx // 12
    new_month = lis_months[new_idx % 12]
    return compose_contract(prefix, new_month, year)


def contract_sort_key(contract: str):
    """Key for sorting contract codes chronologically (year, month_index), prefix ignored."""
    _, month_letter, year = parse_contract(contract)
    return (year, month_to_index[month_letter])


def create_custom_strategy_intraproduct(strategy_name: str, lis_lots: List[int], db_path: str = "positionmanager.db"):
    """Factorize the lots list and store the factorized pattern in the DB.

    The stored pattern is the lots divided by their greatest common divisor.
    """
    non_zero_positive_sizes = [abs(x) for x in lis_lots if x != 0]
    if not non_zero_positive_sizes:
        raise ValueError("Lots list cannot have all zeros.")

    gcd = non_zero_positive_sizes[0]
    for n in non_zero_positive_sizes[1:]:
        gcd = math.gcd(gcd, n)

    lots_lis_factorized = [int(x // gcd) for x in lis_lots]

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS custom_strategies (
            structure_name TEXT PRIMARY KEY,
            structure_lots TEXT
        )
    """)

    lots_json = json.dumps(lots_lis_factorized)
    cur.execute("INSERT OR REPLACE INTO custom_strategies (structure_name, structure_lots) VALUES (?, ?)",
                (strategy_name, lots_json))
    conn.commit()
    conn.close()


def hedge_outrights(lis_contracts: List[str], lis_lots: List[int], db_path: str = "positionmanager.db"):
    """Given outright contracts and lots, attempt to find a matching stored structure and
    compute the multiplier lots for that structure.

    Returns (structure_name, multiplier_lots)
    """
    expanded_lis_contracts, expanded_lis_lots = expand_contracts_and_lots(lis_contracts, lis_lots)

    non_zero_positive_sizes = [abs(x) for x in expanded_lis_lots if x != 0]
    if not non_zero_positive_sizes:
        raise ValueError("Lots list cannot have all zeros.")

    gcd = non_zero_positive_sizes[0]
    for n in non_zero_positive_sizes[1:]:
        gcd = math.gcd(gcd, n)

    lis_lots_factorized = [int(x // gcd) for x in expanded_lis_lots]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT structure_name, structure_lots FROM custom_strategies")
    rows = cursor.fetchall()

    structure_name = None
    sign = 1
    for name, lots_str in rows:
        try:
            stored_lots = json.loads(lots_str)
        except Exception:
            # fallback for legacy literal_eval content
            stored_lots = ast.literal_eval(lots_str)

        if stored_lots == lis_lots_factorized:
            structure_name = name
            sign = 1
            break
        # allow matching the negative pattern (e.g. input [-1,1] matches stored [1,-1])
        if stored_lots == [-x for x in lis_lots_factorized]:
            structure_name = name
            sign = -1
            break

    conn.close()

    if structure_name is None:
        raise ValueError("No matching custom strategy found for factorized lots.")

    # find first non-zero position in factorized pattern to compute multiplier safely
    first_nonzero_index = None
    for idx, v in enumerate(lis_lots_factorized):
        if v != 0:
            first_nonzero_index = idx
            break
    if first_nonzero_index is None:
        raise ValueError("Invalid factorized pattern (all zeros).")

    first_factorized_value = lis_lots_factorized[first_nonzero_index]
    first_actual_value = expanded_lis_lots[first_nonzero_index]

    if first_factorized_value == 0:
        raise ValueError("Unexpected zero in factorized pattern when computing multiplier.")

    num_lots = int(first_actual_value // first_factorized_value)

    # apply sign when matching an inverted pattern
    return structure_name, num_lots * sign


def unhedge_structure_into_outrights(
    lis_structure_names: List[str],
    lis_starting_contracts: List[str],
    lis_num_lots: List[int],
    db_path: str = "positionmanager.db"
) -> Tuple[List[str], List[int]]:
    """Expand a list of named structures (stored in DB) into outright contracts and aggregated lots.

    Returns (final_contracts, final_lots)
    """
    if not (len(lis_structure_names) == len(lis_starting_contracts) == len(lis_num_lots)):
        raise ValueError("All input lists must have equal length.")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    placeholders = ",".join(["?"] * len(lis_structure_names))
    cur.execute(f"SELECT structure_name, structure_lots FROM custom_strategies WHERE structure_name IN ({placeholders})", lis_structure_names)
    rows = cur.fetchall()
    conn.close()

    lots_lookup = {}
    for name, lots_str in rows:
        try:
            lots_lookup[name] = json.loads(lots_str)
        except Exception:
            lots_lookup[name] = ast.literal_eval(lots_str)

    aggregated = {}
    for structure_name, starting_contract, num_lots in zip(lis_structure_names, lis_starting_contracts, lis_num_lots):
        if structure_name not in lots_lookup:
            raise ValueError(f"Strategy '{structure_name}' not found in custom_strategies.")

        lots_pattern = lots_lookup[structure_name]
        n = len(lots_pattern)

        for i in range(n):
            contract = next_contract(starting_contract, i)
            lots = int(lots_pattern[i] * num_lots)
            aggregated[contract] = aggregated.get(contract, 0) + lots

    combined = list(aggregated.items())
    combined_sorted = sorted(combined, key=lambda x: contract_sort_key(x[0]))
    final_contracts = [c for c, l in combined_sorted]
    final_lots = [l for c, l in combined_sorted]

    return final_contracts, final_lots


def implement_hedge(product: str, lis_structure_names: List[str], lis_starting_contracts: List[str], lis_num_lots: List[int], db_path: str = "positionmanager.db"):
    """
    Perform hedging logic and persist results into the product-specific positions table.

    Steps:
    1. Unhedge input structures into outright contracts/lots.
    2. Attempt to find matching hedged structure.
    3. Ensure table + columns exist.
    4. Add hedged structure to base contract.
    5. Subtract input structures at their starting contract ONLY.
    """
    table_name = f"{product}_positions"

    # ---------------------------
    # STEP 1 & 2: COMPUTE HEDGED STRUCTURE
    # ---------------------------
    outright_contracts, outright_lots = unhedge_structure_into_outrights(
        lis_structure_names, lis_starting_contracts, lis_num_lots, db_path=db_path
    )

    try:
        hedged_structure_name, hedged_structure_lots = hedge_outrights(
            outright_contracts, outright_lots, db_path=db_path
        )
    except ValueError:
        # No matching hedged pattern → return machine-readable pattern + contracts
        expanded_contracts, expanded_lots = expand_contracts_and_lots(
            outright_contracts, outright_lots
        )
        non_zero_positive_sizes = [abs(x) for x in expanded_lots if x != 0]
        if not non_zero_positive_sizes:
            raise

        gcd = non_zero_positive_sizes[0]
        for n in non_zero_positive_sizes[1:]:
            gcd = math.gcd(gcd, n)

        lis_lots_factorized = [int(x // gcd) for x in expanded_lots]

        payload = {
            'pattern': lis_lots_factorized,
            'contracts': expanded_contracts
        }

        raise ValueError("MISSING_HEDGED_PATTERN:" + json.dumps(payload))

    hedged_structure_base_contract = outright_contracts[0]

    # ---------------------------
    # STEP 3: DB SETUP
    # ---------------------------
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Ensure base positions table exists
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            contract TEXT PRIMARY KEY,
            lots INTEGER
        )
    """)

    # Read existing columns
    cur.execute(f"PRAGMA table_info('{table_name}')")
    existing_cols = [r[1] for r in cur.fetchall()]

    # Add 'outright' column if missing
    if "outright" not in existing_cols:
        cur.execute(f'ALTER TABLE {table_name} ADD COLUMN "outright" INTEGER DEFAULT 0')
        cur.execute(f'UPDATE {table_name} SET outright = COALESCE(lots, 0)')
        existing_cols.append("outright")

    # ---------------------------
    # STEP 4: VALIDATE INPUT STRUCTURES
    # ---------------------------
    patterns = {}
    contracts_to_ensure_rows = set()
    contracts_to_ensure_rows.add(hedged_structure_base_contract)

    for structure_name, starting_contract, n_lots in zip(
        lis_structure_names, lis_starting_contracts, lis_num_lots
    ):
        cur.execute(
            "SELECT structure_lots FROM custom_strategies WHERE structure_name = ?",
            (structure_name,)
        )
        r = cur.fetchone()
        if not r:
            patterns[structure_name] = None
            contracts_to_ensure_rows.add(starting_contract)
            continue

        # load pattern
        try:
            pattern = json.loads(r[0])
        except Exception:
            pattern = ast.literal_eval(r[0])
        patterns[structure_name] = pattern

        # ensure rows for all contracts in the pattern
        for i in range(len(pattern)):
            contracts_to_ensure_rows.add(next_contract(starting_contract, i))

    # Report missing inputs
    missing = [name for name, patt in patterns.items() if patt is None]
    if missing:
        conn.close()
        raise ValueError("MISSING_STRATEGIES:" + json.dumps(missing))

    # ---------------------------
    # STEP 5: ENSURE STRUCTURE COLUMNS EXIST
    # ---------------------------
    structure_names_set = set(lis_structure_names) | {hedged_structure_name}

    for sname in structure_names_set:
        if sname not in existing_cols:
            cur.execute(f'ALTER TABLE {table_name} ADD COLUMN "{sname}" INTEGER DEFAULT 0')
            existing_cols.append(sname)

    # Ensure rows exist
    for contract in contracts_to_ensure_rows:
        cur.execute(f"SELECT 1 FROM {table_name} WHERE contract = ?", (contract,))
        if not cur.fetchone():
            cur.execute(
                f"INSERT INTO {table_name} (contract, lots, outright) VALUES (?, ?, ?)",
                (contract, 0, 0)
            )

    # ---------------------------
    # STEP 6: APPLY HEDGES
    # ---------------------------
    def add_delta(contract: str, col: str, delta: int):
        cur.execute(
            f'UPDATE {table_name} SET "{col}" = COALESCE("{col}", 0) + ? WHERE contract = ?',
            (delta, contract)
        )

    # Add hedged structure at base contract
    add_delta(hedged_structure_base_contract, hedged_structure_name, hedged_structure_lots)

    # Subtract from each input structure at its starting contract ONLY
    for structure_name, starting_contract, n_lots in zip(
        lis_structure_names, lis_starting_contracts, lis_num_lots
    ):
        add_delta(starting_contract, structure_name, -n_lots)

    conn.commit()
    conn.close()

    return hedged_structure_base_contract, hedged_structure_name, hedged_structure_lots

# Function to clear all hedges and represent all in terms of outrights
def clear_all_hedges(product, db_path: str = "positionmanager.db"):
    """
    Clear all hedged structure columns in <product>_positions.
    After clearing, the 'outright' column will be set equal to 'lots'.

    This resets the table into a pure-outright representation.
    """
    table_name = f"{product}_positions"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Ensure table exists
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            contract TEXT PRIMARY KEY,
            lots INTEGER,
            outright INTEGER
        )
    """)

    # Fetch columns in table
    cur.execute(f"PRAGMA table_info({table_name})")
    cols = [row[1] for row in cur.fetchall()]

    # Identify structure columns
    skip_cols = {"contract", "lots", "outright"}
    structure_cols = [c for c in cols if c not in skip_cols]

    # Set each structure column to 0
    for sc in structure_cols:
        cur.execute(f'UPDATE {table_name} SET "{sc}" = 0')

    # Set outright = lots
    cur.execute(f"UPDATE {table_name} SET outright = COALESCE(lots, 0)")

    conn.commit()
    conn.close()

    return {"status": "ok", "message": "All hedges cleared. Table reset to outright-only."}
if __name__ == "__main__":
    # simple smoke test
    print("lis_months:", lis_months)
