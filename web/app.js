 let currentSuggestion = null;

// Drag & drop
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');

dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    handleFiles(e.dataTransfer.files);
});

fileInput.addEventListener('change', (e) => {
    handleFiles(e.target.files);
});

async function handleFiles(files) {
    const paths = [];
    for (let file of files) {
        // In real app, you'd upload to server or handle locally
        // For now, we'll use file paths (works if running locally)
        paths.push(file.path || file.name);
    }
    
    if (paths.length === 0) return;
    
    // Load images
    const result = await eel.load_images(paths)();
    
    if (result && result.total_pieces > 0) {
        document.getElementById('loadPanel').classList.add('hidden');
        document.getElementById('mainContent').classList.remove('hidden');
        
        updateStats();
        loadNextSuggestion();
    } else {
        alert('No pieces detected. Check image quality and thresholds.');
    }
}

async function loadNextSuggestion() {
    const suggestion = await eel.get_suggestion()();
    
    if (!suggestion) {
        alert('Puzzle complete or no more suggestions!');
        return;
    }
    
    currentSuggestion = suggestion;
    
    // Update reference piece
    document.getElementById('refImage').src = suggestion.ref_image;
    document.getElementById('refInfo').innerHTML = `
        <div><strong>Piece ${suggestion.ref_piece.id}</strong></div>
        <div>Connect on: <strong>${suggestion.side_name}</strong> side</div>
        ${renderTabs(suggestion.ref_piece.tabs)}
    `;
    
    // Update suggested piece
    document.getElementById('pieceImage').src = suggestion.piece_image;
    document.getElementById('pieceInfo').innerHTML = `
        <div><strong>Piece ${suggestion.piece.id}</strong></div>
        <div>Confidence: <strong>${(suggestion.score * 100).toFixed(1)}%</strong></div>
        <div>Source: ${suggestion.piece.source_image}</div>
        <div>Location: (${suggestion.piece.bbox.join(', ')})</div>
        ${renderTabs(suggestion.piece.tabs)}
    `;
    
    updateStats();
}

function renderTabs(tabs) {
    const names = ['Top', 'Right', 'Bottom', 'Left'];
    const symbols = { '1': '↑', '-1': '↓', '0': '—' };
    const classes = { '1': 'tab-out', '-1': 'tab-in', '0': 'tab-flat'};
    
    let html = '<div class="tabs-display">';
    for (let i = 0; i < 4; i++) {
        const cls = classes[tabs[i].toString()];
        html += `<div class="tab-indicator ${cls}">${names[i]}: ${symbols[tabs[i].toString()]}</div>`;
    }
    html += '</div>';
    return html;
}

async function handleFeedback(fits) {
    if (!currentSuggestion) return;
    
    await eel.submit_feedback(
        currentSuggestion.piece.id,
        currentSuggestion.ref_piece.id,
        currentSuggestion.side,
        fits,
        currentSuggestion.position
    )();
    
    loadNextSuggestion();
}

async function updateStats() {
    const stats = await eel.get_stats()();
    
    if (stats) {
        document.getElementById('stat-placed').textContent = stats.placed;
        document.getElementById('stat-remaining').textContent = stats.remaining;
        document.getElementById('stat-total').textContent = stats.total;
        
        const progress = (stats.placed / stats.total) * 100;
        document.getElementById('progress').style.width = progress + '%';
    }
}