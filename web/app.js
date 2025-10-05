// ============================================================================
// GLOBAL STATE
// ============================================================================

let currentSuggestion = null;

// Calibration state
const calibrationState = {
    puzzle: {
        imagePath: null,
        imageData: null,
        loadedImage: null, // Cached Image object
        roi: null,
        backgroundSample: null,
        minArea: 500,
        maxArea: 50000
    },
    pieces: {
        imagePaths: [],
        imageDataList: [],
        loadedImages: [], // Cached Image objects
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

        // Restore visual state when returning to a step
        if (stepNumber === 1 && calibrationState.puzzle.imageData) {
            // Restore puzzle image and ROI overlay
            if (calibrationState.puzzle.roi) {
                drawROIOverlay('canvasPuzzle', calibrationState.puzzle.roi, calibrationState.puzzle.imageData);
            } else {
                loadImageToCanvas('canvasPuzzle', calibrationState.puzzle.imageData);
            }
        } else if (stepNumber === 2 && calibrationState.pieces.imageDataList.length > 0) {
            // Restore pieces image and ROI overlay
            const index = calibrationState.pieces.currentImageIndex;
            if (calibrationState.pieces.roi) {
                drawROIOverlay('canvasPieces', calibrationState.pieces.roi, calibrationState.pieces.imageDataList[index]);
            } else {
                loadImageToCanvas('canvasPieces', calibrationState.pieces.imageDataList[index]);
            }
        }
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

    // Pass base64 image data instead of file path
    const loadResult = await eel.load_puzzle_state(calibrationState.puzzle.imageData)();

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

    // Pass base64 image data instead of file paths
    const loadResult = await eel.load_available_pieces(calibrationState.pieces.imageDataList)();

    if (loadResult.success) {
        availablePiecesCount = loadResult.pieces_count;

        // Update validation summary
        document.getElementById('puzzlePiecesCount').textContent = puzzlePiecesCount;
        document.getElementById('availablePiecesCount').textContent = availablePiecesCount;
        document.getElementById('availableImagesCount').textContent = calibrationState.pieces.imageDataList.length;
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
    // Store absolute path for Eel (works in Electron/desktop apps)
    calibrationState.puzzle.imagePath = file.path || file.webkitRelativePath || file.name;

    const reader = new FileReader();
    reader.onload = (e) => {
        calibrationState.puzzle.imageData = e.target.result;

        // Preload image for faster canvas operations
        const img = new Image();
        img.onload = () => {
            calibrationState.puzzle.loadedImage = img;
            loadImageToCanvas('canvasPuzzle', e.target.result);
            document.getElementById('calibPuzzlePanel').classList.remove('hidden');
            document.getElementById('statusPuzzle').textContent = 'Image loaded. Configure calibration.';
        };
        img.src = e.target.result;
    };
    reader.readAsDataURL(file);
}

// Calibration tools for puzzle
let puzzleMode = 'none'; // 'roi', 'background', 'none'
let roiStart = null;

document.getElementById('btnSelectROIPuzzle').addEventListener('click', () => {
    puzzleMode = 'roi';
    document.getElementById('statusPuzzle').textContent = 'Click and drag to select zone';

    // Update button states
    document.getElementById('btnSelectROIPuzzle').classList.add('active');
    document.getElementById('btnSelectBgPuzzle').classList.remove('active');
});

document.getElementById('btnSelectBgPuzzle').addEventListener('click', () => {
    puzzleMode = 'background';
    document.getElementById('statusPuzzle').textContent = 'Click and drag to select background sample';

    // Update button states
    document.getElementById('btnSelectROIPuzzle').classList.remove('active');
    document.getElementById('btnSelectBgPuzzle').classList.add('active');
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

document.getElementById('minAreaPuzzle').addEventListener('change', async (e) => {
    calibrationState.puzzle.minArea = parseInt(e.target.value);
    // Auto-refresh if debug is on
    if (document.getElementById('debugPuzzle').checked) {
        await previewDetection('puzzle');
    }
});

document.getElementById('maxAreaPuzzle').addEventListener('change', async (e) => {
    calibrationState.puzzle.maxArea = parseInt(e.target.value);
    // Auto-refresh if debug is on
    if (document.getElementById('debugPuzzle').checked) {
        await previewDetection('puzzle');
    }
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

canvasPuzzle.addEventListener('mousemove', (e) => {
    if (!roiStart) {
        return;
    }

    if (puzzleMode === 'none') {
        // Show message once per drag attempt
        if (!roiStart.messageShown) {
            document.getElementById('statusPuzzle').textContent = 'Click "Select Fill Zone" or "Select Background" button first';
            document.getElementById('statusPuzzle').style.color = '#e67e22';
            roiStart.messageShown = true;
            setTimeout(() => {
                document.getElementById('statusPuzzle').style.color = '';
            }, 3000);
        }
        return;
    }

    if (!calibrationState.puzzle.loadedImage) {
        console.log('[DEBUG] mousemove: loadedImage not available');
        return;
    }

    const rect = canvasPuzzle.getBoundingClientRect();
    const scaleX = canvasPuzzle.width / rect.width;
    const scaleY = canvasPuzzle.height / rect.height;

    const currentX = (e.clientX - rect.left) * scaleX;
    const currentY = (e.clientY - rect.top) * scaleY;

    // Redraw image using cached image object (much faster)
    const ctx = canvasPuzzle.getContext('2d');
    ctx.clearRect(0, 0, canvasPuzzle.width, canvasPuzzle.height);
    ctx.drawImage(calibrationState.puzzle.loadedImage, 0, 0);

    // Draw existing ROI if any
    if (calibrationState.puzzle.roi) {
        const [rx, ry, rw, rh] = calibrationState.puzzle.roi;
        ctx.strokeStyle = 'rgba(138, 43, 226, 0.8)';
        ctx.lineWidth = 3;
        ctx.strokeRect(rx, ry, rw, rh);
    }

    // Draw current selection
    ctx.strokeStyle = 'rgba(66, 135, 245, 0.8)';
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 5]);
    const x = Math.min(roiStart.x, currentX);
    const y = Math.min(roiStart.y, currentY);
    const w = Math.abs(currentX - roiStart.x);
    const h = Math.abs(currentY - roiStart.y);
    ctx.strokeRect(x, y, w, h);
    ctx.setLineDash([]);
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

    if (puzzleMode === 'roi') {
        // Set ROI
        calibrationState.puzzle.roi = [Math.round(x), Math.round(y), Math.round(w), Math.round(h)];
        document.getElementById('statusPuzzle').textContent = `Zone set: ${Math.round(w)}x${Math.round(h)}`;
        document.getElementById('btnPreviewPuzzle').classList.remove('disabled');
        drawROIOverlay('canvasPuzzle', calibrationState.puzzle.roi, calibrationState.puzzle.imageData);
        updateCalibrationStatus('puzzle');

        // Deactivate button after successful selection
        document.getElementById('btnSelectROIPuzzle').classList.remove('active');
        puzzleMode = 'none';
    } else if (puzzleMode === 'background') {
        console.log('Getting background color from base64 image');
        console.log('ROI:', [Math.round(x), Math.round(y), Math.round(w), Math.round(h)]);

        try {
            // Get background color - pass base64 image data instead of file path
            const result = await eel.get_background_color(
                calibrationState.puzzle.imageData,
                [Math.round(x), Math.round(y), Math.round(w), Math.round(h)]
            )();

            console.log('Background color result:', result);

            if (result) {
                calibrationState.puzzle.backgroundSample = result.color;
                document.getElementById('statusPuzzle').textContent = `Background color: RGB(${result.color_rgb.join(', ')})`;
                document.getElementById('btnPreviewPuzzle').classList.remove('disabled');
                updateCalibrationStatus('puzzle');

                // Deactivate button after successful selection
                document.getElementById('btnSelectBgPuzzle').classList.remove('active');
                puzzleMode = 'none';
            } else {
                document.getElementById('statusPuzzle').textContent = 'Error: Could not get background color.';
            }
        } catch (error) {
            console.error('Background color error:', error);
            document.getElementById('statusPuzzle').textContent = 'Error: ' + error.message;
        }
    }

    roiStart = null;
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
    calibrationState.pieces.loadedImages = [];

    const fileSelect = document.getElementById('fileSelectPieces');
    fileSelect.innerHTML = '';

    let filesLoaded = 0;

    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        calibrationState.pieces.imagePaths.push(file.path || file.webkitRelativePath || file.name);

        const reader = new FileReader();
        reader.onload = (e) => {
            calibrationState.pieces.imageDataList.push(e.target.result);

            // Preload image for faster canvas operations
            const img = new Image();
            img.onload = () => {
                calibrationState.pieces.loadedImages.push(img);
                filesLoaded++;

                const option = document.createElement('option');
                option.value = calibrationState.pieces.loadedImages.length - 1;
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
            img.src = e.target.result;
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
let piecesMode = 'none'; // 'roi', 'background', 'none'

document.getElementById('btnSelectROIPieces').addEventListener('click', () => {
    piecesMode = 'roi';
    document.getElementById('statusPieces').textContent = 'Click and drag to select ROI';

    // Update button states
    document.getElementById('btnSelectROIPieces').classList.add('active');
    document.getElementById('btnSelectBgPieces').classList.remove('active');
});

document.getElementById('btnSelectBgPieces').addEventListener('click', () => {
    piecesMode = 'background';
    document.getElementById('statusPieces').textContent = 'Click and drag to select background sample';

    // Update button states
    document.getElementById('btnSelectROIPieces').classList.remove('active');
    document.getElementById('btnSelectBgPieces').classList.add('active');
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

document.getElementById('minAreaPieces').addEventListener('change', async (e) => {
    calibrationState.pieces.minArea = parseInt(e.target.value);
    // Auto-refresh if debug is on
    if (document.getElementById('debugPieces').checked) {
        await previewDetection('pieces');
    }
});

document.getElementById('maxAreaPieces').addEventListener('change', async (e) => {
    calibrationState.pieces.maxArea = parseInt(e.target.value);
    // Auto-refresh if debug is on
    if (document.getElementById('debugPieces').checked) {
        await previewDetection('pieces');
    }
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

canvasPieces.addEventListener('mousemove', (e) => {
    if (!roiStartPieces) return;

    if (piecesMode === 'none') {
        // Show message once per drag attempt
        if (!roiStartPieces.messageShown) {
            document.getElementById('statusPieces').textContent = 'Click "Select ROI" or "Select Background" button first';
            document.getElementById('statusPieces').style.color = '#e67e22';
            roiStartPieces.messageShown = true;
            setTimeout(() => {
                document.getElementById('statusPieces').style.color = '';
            }, 3000);
        }
        return;
    }

    const index = calibrationState.pieces.currentImageIndex;
    if (!calibrationState.pieces.loadedImages[index]) return;

    const rect = canvasPieces.getBoundingClientRect();
    const scaleX = canvasPieces.width / rect.width;
    const scaleY = canvasPieces.height / rect.height;

    const currentX = (e.clientX - rect.left) * scaleX;
    const currentY = (e.clientY - rect.top) * scaleY;

    // Redraw image using cached image object (much faster)
    const ctx = canvasPieces.getContext('2d');
    ctx.clearRect(0, 0, canvasPieces.width, canvasPieces.height);
    ctx.drawImage(calibrationState.pieces.loadedImages[index], 0, 0);

    // Draw existing ROI if any
    if (calibrationState.pieces.roi) {
        const [rx, ry, rw, rh] = calibrationState.pieces.roi;
        ctx.strokeStyle = 'rgba(138, 43, 226, 0.8)';
        ctx.lineWidth = 3;
        ctx.strokeRect(rx, ry, rw, rh);
    }

    // Draw current selection
    ctx.strokeStyle = 'rgba(66, 135, 245, 0.8)';
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 5]);
    const x = Math.min(roiStartPieces.x, currentX);
    const y = Math.min(roiStartPieces.y, currentY);
    const w = Math.abs(currentX - roiStartPieces.x);
    const h = Math.abs(currentY - roiStartPieces.y);
    ctx.strokeRect(x, y, w, h);
    ctx.setLineDash([]);
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
    const currentImageData = calibrationState.pieces.imageDataList[calibrationState.pieces.currentImageIndex];

    if (piecesMode === 'roi') {
        // Set ROI
        calibrationState.pieces.roi = [Math.round(x), Math.round(y), Math.round(w), Math.round(h)];
        document.getElementById('statusPieces').textContent = `ROI set: ${Math.round(w)}x${Math.round(h)}`;
        document.getElementById('btnPreviewPieces').classList.remove('disabled');
        drawROIOverlay('canvasPieces', calibrationState.pieces.roi, currentImageData);
        updateCalibrationStatus('pieces');

        // Deactivate button after successful selection
        document.getElementById('btnSelectROIPieces').classList.remove('active');
        piecesMode = 'none';
    } else if (piecesMode === 'background') {
        console.log('Getting background color from base64 image');
        console.log('ROI:', [Math.round(x), Math.round(y), Math.round(w), Math.round(h)]);

        try {
            // Get background color - pass base64 image data instead of file path
            const result = await eel.get_background_color(
                currentImageData,
                [Math.round(x), Math.round(y), Math.round(w), Math.round(h)]
            )();

            console.log('Background color result:', result);

            if (result) {
                calibrationState.pieces.backgroundSample = result.color;
                document.getElementById('statusPieces').textContent = `Background color: RGB(${result.color_rgb.join(', ')})`;
                document.getElementById('btnPreviewPieces').classList.remove('disabled');
                updateCalibrationStatus('pieces');

                // Deactivate button after successful selection
                document.getElementById('btnSelectBgPieces').classList.remove('active');
                piecesMode = 'none';
            } else {
                document.getElementById('statusPieces').textContent = 'Error: Could not get background color.';
            }
        } catch (error) {
            console.error('Background color error:', error);
            document.getElementById('statusPieces').textContent = 'Error: ' + error.message;
        }
    }

    roiStartPieces = null;
});

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

function updateCalibrationStatus(type) {
    const calibration = type === 'puzzle' ? calibrationState.puzzle : calibrationState.pieces;
    const statusId = type === 'puzzle' ? 'calibStatusPuzzle' : 'calibStatusPieces';
    const statusEl = document.getElementById(statusId);

    if (!statusEl) return;

    let html = '<div class="calib-status-items">';

    // ROI status
    if (calibration.roi) {
        const [x, y, w, h] = calibration.roi;
        html += `<div class="status-item status-ok">✓ Fill Zone: ${w}x${h}px</div>`;
    } else {
        html += `<div class="status-item status-none">○ Fill Zone: Not set</div>`;
    }

    // Background status
    if (calibration.backgroundSample) {
        const [b, g, r] = calibration.backgroundSample;
        html += `<div class="status-item status-ok">✓ Background: RGB(${r}, ${g}, ${b})</div>`;
    } else {
        html += `<div class="status-item status-none">○ Background: Not set</div>`;
    }

    html += '</div>';
    statusEl.innerHTML = html;
}

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

function drawROIOverlay(canvasId, roi, imageData) {
    const canvas = document.getElementById(canvasId);
    const ctx = canvas.getContext('2d');
    const img = new Image();

    img.onload = () => {
        canvas.width = img.width;
        canvas.height = img.height;
        ctx.drawImage(img, 0, 0);

        if (roi) {
            const [x, y, w, h] = roi;

            // Draw overlay on outside area
            ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
            ctx.fillRect(0, 0, canvas.width, y); // Top
            ctx.fillRect(0, y, x, h); // Left
            ctx.fillRect(x + w, y, canvas.width - (x + w), h); // Right
            ctx.fillRect(0, y + h, canvas.width, canvas.height - (y + h)); // Bottom

            // Draw ROI border
            ctx.strokeStyle = 'rgba(138, 43, 226, 1)';
            ctx.lineWidth = 3;
            ctx.strokeRect(x, y, w, h);

            // Draw corner markers
            const markerSize = 10;
            ctx.fillStyle = 'rgba(138, 43, 226, 1)';
            // Top-left
            ctx.fillRect(x - 2, y - 2, markerSize, 4);
            ctx.fillRect(x - 2, y - 2, 4, markerSize);
            // Top-right
            ctx.fillRect(x + w - markerSize + 2, y - 2, markerSize, 4);
            ctx.fillRect(x + w - 2, y - 2, 4, markerSize);
            // Bottom-left
            ctx.fillRect(x - 2, y + h - 2, markerSize, 4);
            ctx.fillRect(x - 2, y + h - markerSize + 2, 4, markerSize);
            // Bottom-right
            ctx.fillRect(x + w - markerSize + 2, y + h - 2, markerSize, 4);
            ctx.fillRect(x + w - 2, y + h - markerSize + 2, 4, markerSize);
        }
    };

    img.src = imageData;
}

async function previewDetection(type) {
    const calibration = type === 'puzzle' ? calibrationState.puzzle : calibrationState.pieces;
    const imageData = type === 'puzzle'
        ? calibrationState.puzzle.imageData
        : calibrationState.pieces.imageDataList[calibrationState.pieces.currentImageIndex];

    if (!imageData) {
        const statusId = type === 'puzzle' ? 'statusPuzzle' : 'statusPieces';
        document.getElementById(statusId).textContent = 'No image loaded';
        return;
    }

    console.log(`[DEBUG] Preview detection for ${type}, image data length: ${imageData.length}`);

    try {
        const result = await eel.get_debug_preview(imageData, {
            roi: calibration.roi,
            background_sample: calibration.backgroundSample,
            min_area: calibration.minArea,
            max_area: calibration.maxArea
        })();

        console.log('[DEBUG] Preview result:', result);

        if (result) {
            const canvas = document.getElementById(type === 'puzzle' ? 'canvasPuzzle' : 'canvasPieces');
            const ctx = canvas.getContext('2d');
            const img = new Image();

            img.onload = () => {
                canvas.width = img.width;
                canvas.height = img.height;
                ctx.drawImage(img, 0, 0);

                // Redraw ROI overlay if it exists
                if (calibration.roi) {
                    const [x, y, w, h] = calibration.roi;

                    // Draw overlay on outside area
                    ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
                    ctx.fillRect(0, 0, canvas.width, y); // Top
                    ctx.fillRect(0, y, x, h); // Left
                    ctx.fillRect(x + w, y, canvas.width - (x + w), h); // Right
                    ctx.fillRect(0, y + h, canvas.width, canvas.height - (y + h)); // Bottom

                    // Draw ROI border
                    ctx.strokeStyle = 'rgba(138, 43, 226, 1)';
                    ctx.lineWidth = 3;
                    ctx.strokeRect(x, y, w, h);
                }
            };

            img.src = result.debug_image;

            const statusId = type === 'puzzle' ? 'statusPuzzle' : 'statusPieces';
            const piecesText = result.pieces_count === 0 ? 'No pieces detected' : `Detected ${result.pieces_count} pieces`;
            document.getElementById(statusId).textContent = piecesText +
                (result.pieces_count === 0 ? ' - Try adjusting min/max area or selecting ROI' : '');
        } else {
            const statusId = type === 'puzzle' ? 'statusPuzzle' : 'statusPieces';
            document.getElementById(statusId).textContent = 'Error: Failed to process image (check console for details)';
        }
    } catch (error) {
        console.error('Preview detection error:', error);
        const statusId = type === 'puzzle' ? 'statusPuzzle' : 'statusPieces';
        document.getElementById(statusId).textContent = 'Error: ' + error.message;
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
