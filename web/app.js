// ============================================================================
// GLOBAL STATE
// ============================================================================

let currentSuggestion = null;

// Calibration state
const calibrationState = {
    puzzle: {
        imagePath: null,
        imageData: null,
        roi: null,
        backgroundSample: null,
        minArea: 500,
        maxArea: 50000
    },
    pieces: {
        imagePaths: [],
        imageDataList: [],
        currentImageIndex: 0,
        roi: null,
        backgroundSample: null,
        minArea: 500,
        maxArea: 50000
    }
};

let puzzlePiecesCount = 0;
let availablePiecesCount = 0;

// ============================================================================
// STEP NAVIGATION
// ============================================================================

function showStep(stepNumber) {
    document.getElementById('step1').classList.add('hidden');
    document.getElementById('step2').classList.add('hidden');
    document.getElementById('step3').classList.add('hidden');
    document.getElementById('mainContent').classList.add('hidden');

    if (stepNumber === 'solve') {
        document.getElementById('mainContent').classList.remove('hidden');
    } else {
        document.getElementById(`step${stepNumber}`).classList.remove('hidden');
    }
}

// Navigation buttons
document.getElementById('btnNextStep1').addEventListener('click', async () => {
    // Load puzzle state with calibration
    const result = await eel.set_puzzle_calibration({
        roi: calibrationState.puzzle.roi,
        background_sample: calibrationState.puzzle.backgroundSample,
        min_area: calibrationState.puzzle.minArea,
        max_area: calibrationState.puzzle.maxArea
    })();

    const loadResult = await eel.load_puzzle_state(calibrationState.puzzle.imagePath)();

    if (loadResult.success) {
        puzzlePiecesCount = loadResult.pieces_count;
        showStep(2);
    } else {
        showError('Failed to load puzzle state: ' + loadResult.error);
    }
});

document.getElementById('btnBackStep2').addEventListener('click', () => {
    showStep(1);
});

document.getElementById('btnNextStep2').addEventListener('click', async () => {
    // Load available pieces with calibration
    const result = await eel.set_pieces_calibration({
        roi: calibrationState.pieces.roi,
        background_sample: calibrationState.pieces.backgroundSample,
        min_area: calibrationState.pieces.minArea,
        max_area: calibrationState.pieces.maxArea
    })();

    const loadResult = await eel.load_available_pieces(calibrationState.pieces.imagePaths)();

    if (loadResult.success) {
        availablePiecesCount = loadResult.pieces_count;

        // Update validation summary
        document.getElementById('puzzlePiecesCount').textContent = puzzlePiecesCount;
        document.getElementById('availablePiecesCount').textContent = availablePiecesCount;
        document.getElementById('availableImagesCount').textContent = calibrationState.pieces.imagePaths.length;
        document.getElementById('totalPiecesCount').textContent = puzzlePiecesCount + availablePiecesCount;

        showStep(3);
    } else {
        showError('Failed to load available pieces: ' + loadResult.error);
    }
});

document.getElementById('btnBackStep3').addEventListener('click', () => {
    showStep(2);
});

document.getElementById('btnStartSolving').addEventListener('click', async () => {
    const result = await eel.start_solving()();

    if (result.success) {
        showStep('solve');
        updateStats();
        loadNextSuggestion();
    } else {
        showError('Failed to start solving: ' + result.error);
    }
});

// ============================================================================
// STEP 1: PUZZLE STATE CALIBRATION
// ============================================================================

const dropZonePuzzle = document.getElementById('dropZonePuzzle');
const fileInputPuzzle = document.getElementById('fileInputPuzzle');

dropZonePuzzle.addEventListener('click', () => fileInputPuzzle.click());

dropZonePuzzle.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZonePuzzle.classList.add('dragover');
});

dropZonePuzzle.addEventListener('dragleave', () => {
    dropZonePuzzle.classList.remove('dragover');
});

dropZonePuzzle.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZonePuzzle.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        handlePuzzleFile(e.dataTransfer.files[0]);
    }
});

fileInputPuzzle.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handlePuzzleFile(e.target.files[0]);
    }
});

function handlePuzzleFile(file) {
    calibrationState.puzzle.imagePath = file.path || file.name;

    const reader = new FileReader();
    reader.onload = (e) => {
        calibrationState.puzzle.imageData = e.target.result;
        document.getElementById('calibPuzzlePanel').classList.remove('hidden');
        loadImageToCanvas('canvasPuzzle', e.target.result);
        document.getElementById('statusPuzzle').textContent = 'Image loaded. Configure calibration.';
    };
    reader.readAsDataURL(file);
}

// Calibration tools for puzzle
let roiSelectorActive = false;
let roiStart = null;

document.getElementById('btnSelectROIPuzzle').addEventListener('click', () => {
    roiSelectorActive = true;
    document.getElementById('statusPuzzle').textContent = 'Click and drag to select ROI';
});

document.getElementById('btnSelectBgPuzzle').addEventListener('click', () => {
    roiSelectorActive = false;
    document.getElementById('statusPuzzle').textContent = 'Click and drag to select background sample';
});

document.getElementById('btnPreviewPuzzle').addEventListener('click', async () => {
    await previewDetection('puzzle');
});

document.getElementById('debugPuzzle').addEventListener('change', async (e) => {
    if (e.target.checked) {
        await previewDetection('puzzle');
    } else {
        loadImageToCanvas('canvasPuzzle', calibrationState.puzzle.imageData);
    }
});

document.getElementById('minAreaPuzzle').addEventListener('change', (e) => {
    calibrationState.puzzle.minArea = parseInt(e.target.value);
});

document.getElementById('maxAreaPuzzle').addEventListener('change', (e) => {
    calibrationState.puzzle.maxArea = parseInt(e.target.value);
});

// Canvas interaction for puzzle
const canvasPuzzle = document.getElementById('canvasPuzzle');

canvasPuzzle.addEventListener('mousedown', (e) => {
    const rect = canvasPuzzle.getBoundingClientRect();
    const scaleX = canvasPuzzle.width / rect.width;
    const scaleY = canvasPuzzle.height / rect.height;

    roiStart = {
        x: (e.clientX - rect.left) * scaleX,
        y: (e.clientY - rect.top) * scaleY
    };
});

canvasPuzzle.addEventListener('mouseup', async (e) => {
    if (!roiStart) return;

    const rect = canvasPuzzle.getBoundingClientRect();
    const scaleX = canvasPuzzle.width / rect.width;
    const scaleY = canvasPuzzle.height / rect.height;

    const roiEnd = {
        x: (e.clientX - rect.left) * scaleX,
        y: (e.clientY - rect.top) * scaleY
    };

    const x = Math.min(roiStart.x, roiEnd.x);
    const y = Math.min(roiStart.y, roiEnd.y);
    const w = Math.abs(roiEnd.x - roiStart.x);
    const h = Math.abs(roiEnd.y - roiStart.y);

    if (roiSelectorActive) {
        // Set ROI
        calibrationState.puzzle.roi = [Math.round(x), Math.round(y), Math.round(w), Math.round(h)];
        document.getElementById('statusPuzzle').textContent = `ROI set: ${Math.round(w)}x${Math.round(h)}`;
        document.getElementById('btnPreviewPuzzle').classList.remove('disabled');
    } else {
        // Get background color
        const result = await eel.get_background_color(
            calibrationState.puzzle.imagePath,
            [Math.round(x), Math.round(y), Math.round(w), Math.round(h)]
        )();

        if (result) {
            calibrationState.puzzle.backgroundSample = result.color;
            document.getElementById('statusPuzzle').textContent = `Background color: RGB(${result.color_rgb.join(', ')})`;
            document.getElementById('btnPreviewPuzzle').classList.remove('disabled');
        }
    }

    roiStart = null;
    roiSelectorActive = false;
});

// ============================================================================
// STEP 2: AVAILABLE PIECES CALIBRATION
// ============================================================================

const dropZonePieces = document.getElementById('dropZonePieces');
const fileInputPieces = document.getElementById('fileInputPieces');

dropZonePieces.addEventListener('click', () => fileInputPieces.click());

dropZonePieces.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZonePieces.classList.add('dragover');
});

dropZonePieces.addEventListener('dragleave', () => {
    dropZonePieces.classList.remove('dragover');
});

dropZonePieces.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZonePieces.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        handlePiecesFiles(e.dataTransfer.files);
    }
});

fileInputPieces.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handlePiecesFiles(e.target.files);
    }
});

function handlePiecesFiles(files) {
    calibrationState.pieces.imagePaths = [];
    calibrationState.pieces.imageDataList = [];

    const fileSelect = document.getElementById('fileSelectPieces');
    fileSelect.innerHTML = '';

    let filesLoaded = 0;

    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        calibrationState.pieces.imagePaths.push(file.path || file.name);

        const reader = new FileReader();
        reader.onload = (e) => {
            calibrationState.pieces.imageDataList.push(e.target.result);
            filesLoaded++;

            const option = document.createElement('option');
            option.value = i;
            option.textContent = file.name;
            fileSelect.appendChild(option);

            if (filesLoaded === 1) {
                // Load first image
                loadImageToCanvas('canvasPieces', e.target.result);
                document.getElementById('calibPiecesPanel').classList.remove('hidden');
            }

            if (filesLoaded === files.length) {
                document.getElementById('statusPieces').textContent = `${filesLoaded} images loaded. Configure calibration.`;
            }
        };
        reader.readAsDataURL(file);
    }
}

document.getElementById('fileSelectPieces').addEventListener('change', (e) => {
    const index = parseInt(e.target.value);
    calibrationState.pieces.currentImageIndex = index;
    loadImageToCanvas('canvasPieces', calibrationState.pieces.imageDataList[index]);
});

// Calibration tools for pieces
document.getElementById('btnSelectROIPieces').addEventListener('click', () => {
    roiSelectorActive = true;
    document.getElementById('statusPieces').textContent = 'Click and drag to select ROI';
});

document.getElementById('btnSelectBgPieces').addEventListener('click', () => {
    roiSelectorActive = false;
    document.getElementById('statusPieces').textContent = 'Click and drag to select background sample';
});

document.getElementById('btnPreviewPieces').addEventListener('click', async () => {
    await previewDetection('pieces');
});

document.getElementById('debugPieces').addEventListener('change', async (e) => {
    if (e.target.checked) {
        await previewDetection('pieces');
    } else {
        const index = calibrationState.pieces.currentImageIndex;
        loadImageToCanvas('canvasPieces', calibrationState.pieces.imageDataList[index]);
    }
});

document.getElementById('minAreaPieces').addEventListener('change', (e) => {
    calibrationState.pieces.minArea = parseInt(e.target.value);
});

document.getElementById('maxAreaPieces').addEventListener('change', (e) => {
    calibrationState.pieces.maxArea = parseInt(e.target.value);
});

// Canvas interaction for pieces
const canvasPieces = document.getElementById('canvasPieces');
let roiStartPieces = null;

canvasPieces.addEventListener('mousedown', (e) => {
    const rect = canvasPieces.getBoundingClientRect();
    const scaleX = canvasPieces.width / rect.width;
    const scaleY = canvasPieces.height / rect.height;

    roiStartPieces = {
        x: (e.clientX - rect.left) * scaleX,
        y: (e.clientY - rect.top) * scaleY
    };
});

canvasPieces.addEventListener('mouseup', async (e) => {
    if (!roiStartPieces) return;

    const rect = canvasPieces.getBoundingClientRect();
    const scaleX = canvasPieces.width / rect.width;
    const scaleY = canvasPieces.height / rect.height;

    const roiEnd = {
        x: (e.clientX - rect.left) * scaleX,
        y: (e.clientY - rect.top) * scaleY
    };

    const x = Math.min(roiStartPieces.x, roiEnd.x);
    const y = Math.min(roiStartPieces.y, roiEnd.y);
    const w = Math.abs(roiEnd.x - roiStartPieces.x);
    const h = Math.abs(roiEnd.y - roiStartPieces.y);

    const currentPath = calibrationState.pieces.imagePaths[calibrationState.pieces.currentImageIndex];

    if (roiSelectorActive) {
        // Set ROI
        calibrationState.pieces.roi = [Math.round(x), Math.round(y), Math.round(w), Math.round(h)];
        document.getElementById('statusPieces').textContent = `ROI set: ${Math.round(w)}x${Math.round(h)}`;
        document.getElementById('btnPreviewPieces').classList.remove('disabled');
    } else {
        // Get background color
        const result = await eel.get_background_color(
            currentPath,
            [Math.round(x), Math.round(y), Math.round(w), Math.round(h)]
        )();

        if (result) {
            calibrationState.pieces.backgroundSample = result.color;
            document.getElementById('statusPieces').textContent = `Background color: RGB(${result.color_rgb.join(', ')})`;
            document.getElementById('btnPreviewPieces').classList.remove('disabled');
        }
    }

    roiStartPieces = null;
    roiSelectorActive = false;
});

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

function loadImageToCanvas(canvasId, imageData) {
    const canvas = document.getElementById(canvasId);
    const ctx = canvas.getContext('2d');
    const img = new Image();

    img.onload = () => {
        canvas.width = img.width;
        canvas.height = img.height;
        ctx.drawImage(img, 0, 0);
    };

    img.src = imageData;
}

async function previewDetection(type) {
    const calibration = type === 'puzzle' ? calibrationState.puzzle : calibrationState.pieces;
    const imagePath = type === 'puzzle'
        ? calibrationState.puzzle.imagePath
        : calibrationState.pieces.imagePaths[calibrationState.pieces.currentImageIndex];

    const result = await eel.get_debug_preview(imagePath, {
        roi: calibration.roi,
        background_sample: calibration.backgroundSample,
        min_area: calibration.minArea,
        max_area: calibration.maxArea
    })();

    if (result) {
        const canvas = document.getElementById(type === 'puzzle' ? 'canvasPuzzle' : 'canvasPieces');
        const ctx = canvas.getContext('2d');
        const img = new Image();

        img.onload = () => {
            canvas.width = img.width;
            canvas.height = img.height;
            ctx.drawImage(img, 0, 0);
        };

        img.src = result.debug_image;

        const statusId = type === 'puzzle' ? 'statusPuzzle' : 'statusPieces';
        document.getElementById(statusId).textContent = `Detected ${result.pieces_count} pieces`;
    }
}

// ============================================================================
// SOLVING INTERFACE (from original app.js)
// ============================================================================

async function loadNextSuggestion() {
    const suggestion = await eel.get_suggestion()();

    if (!suggestion) {
        showError('Puzzle complete or no more suggestions!', 'success');
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

function showError(message, type = 'error') {
    const errorDiv = document.getElementById('errorMessage');
    const errorText = document.getElementById('errorText');
    const errorIcon = errorDiv.querySelector('.error-icon');

    errorText.textContent = message;

    // Change style based on type
    if (type === 'success') {
        errorDiv.style.background = 'linear-gradient(135deg, rgba(39, 174, 96, 0.9), rgba(34, 153, 84, 0.9))';
        errorIcon.textContent = '✓';
    } else {
        errorDiv.style.background = 'linear-gradient(135deg, rgba(231, 76, 60, 0.9), rgba(192, 57, 43, 0.9))';
        errorIcon.textContent = '⚠️';
    }

    errorDiv.classList.remove('hidden');

    // Auto-hide after 5 seconds
    setTimeout(() => {
        hideError();
    }, 5000);
}

function hideError() {
    document.getElementById('errorMessage').classList.add('hidden');
}
