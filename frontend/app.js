// app.js — patched version

async function loadPositions() {
  const productSelect = document.getElementById('product-select');
  const product = productSelect ? productSelect.value : 'CL';

  try {
    const resp = await fetch(`/api/positions/${product}`);
    if (!resp.ok) throw new Error('Network response was not ok');
    const data = await resp.json();

    const container = document.getElementById('positions-grid');
    if (!container) {
      console.error('positions-grid container not found in DOM');
      return;
    }

    const contracts = data.contracts || [];
    const rows = data.rows || [];

    const dataJSON = JSON.stringify({ contracts, rows });
    if (window._prevDataJSON === dataJSON) return;

    // preserve horizontal scroll left
    const oldGridWrap = container.querySelector('.grid-table');
    const oldScrollLeft = oldGridWrap ? oldGridWrap.scrollLeft : 0;

    if (contracts.length === 0 && rows.length === 0) {
      container.innerHTML = '<div class="loading">No positions found for ' + product + '.</div>';
      window._prevDataJSON = dataJSON;
      return;
    }

    buildGrid(contracts, rows, oldScrollLeft);
    window._prevDataJSON = dataJSON;
  } catch (err) {
    console.error(err);
    const container = document.getElementById('positions-grid');
    if (container) {
      container.innerHTML = `<div class="loading">Error loading data: ${err.message}</div>`;
    } else {
      alert('Error loading data: ' + err.message);
    }
  }
}

let _isLoading = false;
async function pollLoop(intervalMs = 1000) {
  await loadPositions();
  setInterval(async () => {
    if (_isLoading) return;
    try {
      _isLoading = true;
      await loadPositions();
    } finally {
      _isLoading = false;
    }
  }, intervalMs);
}

document.addEventListener('DOMContentLoaded', () => {
  const selector = document.getElementById('product-select');
  if (selector) {
    selector.addEventListener('change', () => {
      window._prevDataJSON = null;
      document.getElementById('positions-grid').innerHTML = '<div class="loading">Loading…</div>';
      loadPositions();
    });
  }
  pollLoop(1000);
});

function buildGrid(contracts, rows, restoreScrollLeft = 0) {
  const container = document.getElementById('positions-grid');
  container.innerHTML = '';

  const gridWrap = document.createElement('div');
  gridWrap.className = 'grid-table';

  const grid = document.createElement('div');
  grid.className = 'grid';

  grid.style.gridTemplateColumns = `160px repeat(${contracts.length}, 1fr)`;

  // header label
  const headerLabel = document.createElement('div');
  headerLabel.className = 'cell header sticky';
  headerLabel.textContent = '';
  grid.appendChild(headerLabel);

  // contract headers
  contracts.forEach(c => {
    const h = document.createElement('div');
    h.className = 'cell header';
    h.textContent = c;
    grid.appendChild(h);
  });

  // rows
  rows.forEach(row => {
    const label = document.createElement('div');
    label.className = 'cell label sticky';
    label.textContent = row.name;
    grid.appendChild(label);

    (row.lots || []).forEach((l, idx) => {
      const cell = document.createElement('div');
      cell.className = 'cell total-cell';
      cell.dataset.structure = row.name;
      cell.dataset.contract = contracts[idx] || '';

      // ensure numeric rendering
      const num = Number(l) || 0;

      if (num === 0) {
        // zero → blank cell
        const blank = document.createElement('span');
        blank.textContent = '';
        blank.className = 'zero';
        cell.appendChild(blank);
      } else {
        const span = document.createElement('span');
        span.textContent = String(num);
        span.className = num > 0 ? 'positive' : 'negative';
        cell.appendChild(span);
      }
      grid.appendChild(cell);
    });
  });

  gridWrap.appendChild(grid);
  container.appendChild(gridWrap);

  if (restoreScrollLeft && gridWrap) {
    gridWrap.scrollLeft = restoreScrollLeft;
  }

  attachCellSelectionHandlers();
}

function attachCellSelectionHandlers() {
  const panel = document.getElementById('selection-panel');
  if (!panel) return;
  panel.innerHTML = '';
  window._selectedCells = [];

  const cells = document.querySelectorAll('.grid .cell.total-cell');
  cells.forEach(cell => {

    // 🚫 BLOCK CLICKING ON TOTAL ROW
    // The "Total" row comes through as structure = "Total"
    if (cell.dataset.structure === "Total") {
      cell.classList.add("total-row-disabled"); // optional CSS styling
      return; // prevent attaching click handler
    }

    // normal handling for real rows
    cell.addEventListener('click', (e) => {
      if (!e.ctrlKey) {
        clearSelection();
      }
      toggleCellSelection(cell);
    });
  });
}

function toggleCellSelection(cell) {
  const panel = document.getElementById('selection-panel');
  if (!panel) return;

  const structure = cell.dataset.structure;
  const contract = cell.dataset.contract;
  const span = cell.querySelector('span');
  const displayed = span ? span.textContent.trim() : cell.textContent.trim();

  const key = `${structure}||${contract}`;
  const idx = (window._selectedCells || []).findIndex(s => s.key === key);
  if (idx >= 0) {
    // deselect
    const removed = window._selectedCells.splice(idx, 1)[0];
    if (removed && removed.element) removed.element.classList.remove('selected');
  } else {
    // select (store reference to element and current value)
    window._selectedCells.push({
      key,
      structure,
      contract,
      element: cell,
      value: displayed
    });
    cell.classList.add('selected');
  }

  renderSelectionPanel();
}

function clearSelection() {
  (window._selectedCells || []).forEach(s => {
    if (s.element) s.element.classList.remove('selected');
  });
  window._selectedCells = [];
  const panel = document.getElementById('selection-panel');
  if (panel) panel.innerHTML = '';
}

function renderSelectionPanel() {
  const panel = document.getElementById('selection-panel');
  if (!panel) return;
  panel.innerHTML = '';

  if (!window._selectedCells || window._selectedCells.length === 0) return;

  const list = document.createElement('div');
  list.className = 'selected-list';

  window._selectedCells.forEach((s, i) => {
    const item = document.createElement('div');
    item.className = 'selected-item';

    const label = document.createElement('div');
    label.textContent = `${s.structure} — ${s.contract}`;

    const input = document.createElement('input');
    input.type = 'number';
    input.value = s.value;
    input.min = -1000000;

    // live-update both the selected object and the grid cell UI
    input.oninput = (e) => {
      s.value = e.target.value;
      // update displayed cell value immediately for feedback
      if (s.element) {
        const sp = s.element.querySelector('span');
        const valNum = Number(s.value) || 0;
        if (sp) {
          sp.textContent = String(valNum);
          if (valNum === 0) {
            sp.textContent = '';
            sp.className = 'zero';
          } else {
            sp.textContent = String(valNum);
            sp.className = valNum > 0 ? 'positive' : 'negative';
          }
        }
      }
    };

    const removeBtn = document.createElement('button');
    removeBtn.textContent = 'x';
    removeBtn.onclick = () => {
      if (s.element) s.element.classList.remove('selected');
      window._selectedCells = window._selectedCells.filter(x => x.key !== s.key);
      renderSelectionPanel();
    };

    item.appendChild(label);
    item.appendChild(input);
    item.appendChild(removeBtn);
    list.appendChild(item);
  });

  const apply = document.createElement('button');
  apply.className = 'apply-btn';
  apply.textContent = 'Apply Hedge (' + (document.getElementById('product-select').value) + ')';
  apply.onclick = applyHedgeFromSelection;

  panel.appendChild(list);
  panel.appendChild(apply);
}

async function applyHedgeFromSelection() {
  if (!window._selectedCells || window._selectedCells.length === 0) return;

  const product = document.getElementById('product-select').value;

  const lis_structure_names = [];
  const lis_starting_contracts = [];
  const lis_num_lots = [];

  window._selectedCells.forEach(s => {
    lis_structure_names.push(s.structure);
    lis_starting_contracts.push(s.contract);
    // parse as integer, default 0
    lis_num_lots.push(parseInt(String(s.value).trim(), 10) || 0);
  });

  const payload = {
    product: product,
    lis_structure_names,
    lis_starting_contracts,
    lis_num_lots
  };

  try {
    const resp = await fetch('/api/implement_hedge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await resp.json();

    if (!resp.ok) {
      // handle missing strategies (create them interactively)
      if (data && data.error === 'missing_strategies' && Array.isArray(data.missing)) {
        for (const missingName of data.missing) {
          const userInput = window.prompt(`Structure '${missingName}' not found. Enter pattern as a JS array (e.g. [1,-1]) to create it, or cancel to abort:`);
          if (userInput === null) throw new Error('Operation cancelled by user');

          let pattern = null;
          try {
            // eslint-disable-next-line no-eval
            pattern = eval(userInput);
            if (!Array.isArray(pattern)) throw new Error('Not an array');
          } catch (err) {
            throw new Error('Invalid pattern provided for ' + missingName);
          }

          const createResp = await fetch('/api/create_strategy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ structure_name: missingName, pattern })
          });
          const createData = await createResp.json();
          if (!createResp.ok) throw new Error(createData.error || 'Failed to create strategy ' + missingName);
        }

        // retry once
        const retryResp = await fetch('/api/implement_hedge', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const retryData = await retryResp.json();
        if (!retryResp.ok) throw new Error(retryData.error || 'Implement hedge failed on retry');

        clearSelection();
        await loadPositions();
        console.log(`Hedge applied: ${retryData.hedged_name} @ ${retryData.base_contract} (+${retryData.hedged_lots})`);

        return;
      }

      // missing hedged pattern: create suggested hedged structure name
      if (data && data.error === 'missing_hedged_pattern' && data.payload) {
        const pattern = data.payload.pattern;
        const suggested = window.prompt(`No stored structure matches pattern ${JSON.stringify(pattern)}. Enter a name to create for this pattern:`, 'new-structure');
        if (suggested === null) throw new Error('Operation cancelled by user');

        const createResp = await fetch('/api/create_strategy', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ structure_name: suggested, pattern })
        });
        const createData = await createResp.json();
        if (!createResp.ok) throw new Error(createData.error || 'Failed to create strategy ' + suggested);

        const retryResp2 = await fetch('/api/implement_hedge', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const retryData2 = await retryResp2.json();
        if (!retryResp2.ok) throw new Error(retryData2.error || 'Implement hedge failed on retry');

        clearSelection();
        await loadPositions();
        console.log(`Hedge applied: ${retryData2.hedged_name} @ ${retryData2.base_contract} (+${retryData2.hedged_lots})`);

        return;
      }

      throw new Error(data.error || 'Implement hedge failed');
    }

    // success
    clearSelection();
    await loadPositions();
    console.log(`Hedge applied: ${data.hedged_name} @ ${data.base_contract} (+${data.hedged_lots})`);

  } catch (err) {
    alert('Error: ' + err.message);
    console.error(err);
  }
}