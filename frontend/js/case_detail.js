const token = localStorage.getItem('token');
const urlParams = new URLSearchParams(window.location.search);
const caseId = urlParams.get('id');

if (!token || !caseId) {
    window.location.href = 'dashboard.html';
}

// Global scope for button logic
let userRole = null;

async function init() {
    try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        userRole = payload.role;
        const rank = payload.rank || userRole;

        const currentUser = await API.getMe(token);

        // Display Profile
        document.getElementById('userNameDisplay').textContent = currentUser.username;
        const roleDisplay = document.getElementById('userRoleDisplay');
        if (roleDisplay) {
            roleDisplay.textContent = rank.toUpperCase();
        }

        // Load Case Info
        const caseInfo = await API.getCase(token, caseId);
        renderCaseInfo(caseInfo);

        // Show Close Button if Active and Authorized
        // Constables cannot close cases. All others (SI, SHO, SP) can.
        if (caseInfo.status === 'active' &&
            !['constable', 'head_constable'].includes(userRole)) {
            document.getElementById('closeCaseBtn').classList.remove('d-none');
        }

        // Load Evidence
        loadEvidence();

    } catch (err) {
        console.error(err);
        alert("Failed to load case data");
    }
}

async function closeCase() {
    if (!confirm("Are you sure you want to mark this case as SOLVED/CLOSED? This action cannot be easily undone.")) {
        return;
    }

    try {
        await API.updateCaseStatus(token, caseId, "closed");
        showAlert('success', "Case marked as Closed successfully.");
        // Small delay to let toast show
        setTimeout(() => window.location.reload(), 1500);
    } catch (err) {
        showAlert('danger', "Failed to close case: " + err.message);
    }
}

function renderCaseInfo(c) {
    document.getElementById('caseTitle').innerText = `Case #${c.fir_number}`;
    document.getElementById('firNumber').innerText = c.fir_number;
    document.getElementById('policeStation').innerText = c.police_station;
    document.getElementById('caseType').innerText = c.case_type;
    document.getElementById('caseDesc').innerText = c.description || '-';
    document.getElementById('createdAt').innerText = new Date(c.created_at).toLocaleString();

    document.getElementById('caseStatusBadge').innerText = c.status;
    document.getElementById('caseStatusBadge').className = `badge bg-${c.status === 'active' ? 'success' : 'secondary'} fs-6`;
}

async function loadEvidence() {
    try {
        const evidenceList = await API.getEvidence(token, caseId);
        const tbody = document.getElementById('evidenceTableBody');
        tbody.innerHTML = '';

        if (evidenceList.length === 0) {
            document.getElementById('noEvidenceMsg').classList.remove('d-none');
            return;
        }
        document.getElementById('noEvidenceMsg').classList.add('d-none');

        evidenceList.forEach(e => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${e.original_filename}</td>
                <td><span class="badge bg-info text-dark">${e.file_type}</span></td>
                <td><code title="${e.file_hash}">${e.file_hash.substring(0, 8)}...</code></td>
                <td class="text-center">
                    <button class="btn btn-sm btn-outline-primary" onclick="viewEvidence(${e.id}, '${e.original_filename}', '${e.file_hash}')">
                        <i class="bi bi-eye"></i> View
                    </button>
                </td>
                <td class="text-end pe-3">
                    <button class="btn btn-sm btn-outline-secondary" onclick="downloadFile(${e.id})">
                        <i class="bi bi-download"></i> Download
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });

    } catch (err) {
        console.error("Failed to load evidence", err);
    }
}

async function viewEvidence(id, filename, integrityHash) {
    console.log(`Viewing: ${filename} (ID: ${id})`);

    // UI Setup
    const modalEl = document.getElementById('viewModal');
    if (!modalEl) { console.error("Modal not found"); return; }

    let modal = bootstrap.Modal.getInstance(modalEl);
    if (!modal) { modal = new bootstrap.Modal(modalEl); }

    const contentDiv = document.getElementById('viewerContent');
    const metaSpan = document.getElementById('evidenceMeta');

    metaSpan.textContent = `File: ${filename} | Hash: ${integrityHash ? integrityHash.substring(0, 10) : 'N/A'}...`;
    contentDiv.innerHTML = '<div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div><div class="text-dark mt-2 fw-medium">Decrypting & Rendering Evidence...</div>';

    modal.show(); // Show early for loading state

    const streamUrl = `${API_URL}/files/view/${id}?token=${token}`;
    const ext = filename.split('.').pop().toLowerCase();

    try {
        let html = '';

        // 1. Images
        if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'].includes(ext)) {
            html = `<img src="${streamUrl}" class="img-fluid rounded" style="max-height: 70vh; object-fit: contain;">`;
            contentDiv.innerHTML = html;
        }

        // 2. Video
        else if (['mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv'].includes(ext)) {
            html = `
                <video controls autoplay class="w-100" style="max-height: 70vh;">
                    <source src="${streamUrl}" type="video/mp4">
                    <source src="${streamUrl}" type="video/webm">
                    <div class="text-white p-4">
                        <i class="bi bi-play-circle-fill fs-1"></i>
                        <p>Browser cannot playback this format directly.</p>
                        <button class="btn btn-primary" onclick="downloadFile(${id})">Download to Play</button>
                    </div>
                </video>`;
            contentDiv.innerHTML = html;
        }

        // 3. Audio
        else if (['mp3', 'wav', 'ogg', 'm4a'].includes(ext)) {
            html = `
                <div class="text-center p-5">
                    <i class="bi bi-file-music-fill fs-1 text-info animate-pulse mb-3 d-block"></i>
                    <audio controls autoplay class="w-100" style="max-width: 500px;">
                        <source src="${streamUrl}">
                        Your browser does not support audio element.
                    </audio>
                </div>`;
            contentDiv.innerHTML = html;
        }

        // 4. PDF
        else if (ext === 'pdf') {
            html = `<iframe src="${streamUrl}" width="100%" height="700px" style="border:none; border-radius: 8px;"></iframe>`;
            contentDiv.innerHTML = html;
        }

        // 5. Spreadsheets (XSLX, CSV, ODTS) -> SheetJS
        else if (['xlsx', 'xls', 'csv', 'ods'].includes(ext)) {
            if (typeof XLSX === 'undefined') {
                throw new Error("SheetJS library (XLSX) is not loaded. Please check your internet connection.");
            }
            const resp = await fetch(streamUrl);
            if (!resp.ok) throw new Error("Failed to fetch file content.");

            const blob = await resp.blob();
            const buffer = await blob.arrayBuffer();

            try {
                const wb = XLSX.read(buffer, { type: 'array' });
                if (!wb.SheetNames || wb.SheetNames.length === 0) {
                    throw new Error("Spreadsheet contains no sheets.");
                }
                const ws = wb.Sheets[wb.SheetNames[0]]; // First sheet
                const tblHtml = XLSX.utils.sheet_to_html(ws, { id: "excelTable", className: "table table-striped table-bordered table-sm" });
                contentDiv.innerHTML = `<div class="bg-white p-2 rounded border" style="max-height: 70vh; overflow: auto; text-align: left;">${tblHtml}</div>`;
            } catch (e) {
                console.error("SheetJS Error:", e);
                throw new Error("Failed to parse spreadsheet: " + e.message);
            }
        }

        // 6. Documents (DOCX) -> Mammoth
        else if (ext === 'docx') {
            const resp = await fetch(streamUrl);
            const blob = await resp.blob();
            const arrayBuffer = await blob.arrayBuffer();

            mammoth.convertToHtml({ arrayBuffer: arrayBuffer })
                .then(result => {
                    contentDiv.innerHTML = `<div class="bg-white text-dark p-4 rounded text-start" style="max-height: 70vh; overflow: auto;">${result.value}</div>`;
                })
                .catch(err => {
                    throw new Error("Docx Rendering Failed: " + err.message);
                });
        }

        // 7. Text / Logs
        else if (['txt', 'log', 'json', 'xml', 'py', 'js', 'md'].includes(ext)) {
            const resp = await fetch(streamUrl);
            const text = await resp.text();
            contentDiv.innerHTML = `<pre class="text-start text-dark bg-light p-3 rounded border" style="max-height: 70vh; overflow: auto; font-family: monospace;">${text.replace(/</g, '&lt;')}</pre>`;
        }

        // 8. Archives (ZIP) -> JSZip
        else if (ext === 'zip') {
            const resp = await fetch(streamUrl);
            const blob = await resp.blob();
            const zip = await JSZip.loadAsync(blob);

            let listHtml = '<ul class="list-group list-group-flush text-start">';
            zip.forEach((relativePath, zipEntry) => {
                const icon = zipEntry.dir ? 'bi-folder-fill text-warning' : 'bi-file-earmark-text text-light';
                listHtml += `<li class="list-group-item bg-transparent text-white border-secondary"><i class="bi ${icon} me-2"></i> ${relativePath}</li>`;
            });
            listHtml += '</ul>';

            contentDiv.innerHTML = `<div class="p-3" style="max-height: 70vh; overflow: auto;">
                <h6 class="text-info mb-3"><i class="bi bi-file-zip-fill"></i> Archive Contents</h6>
                ${listHtml}
            </div>`;
        }

        // Fallback
        else {
            contentDiv.innerHTML = `<div class="text-dark p-5">
                <i class="bi bi-file-earmark-binary fs-1 opacity-50"></i>
                <p class="mt-3">Preview not available for this file type (${ext}).</p>
                <button class="btn btn-primary btn-sm mt-2" onclick="downloadFile(${id})">Download to View</button>
            </div>`;
        }

    } catch (err) {
        console.error("Viewer Error:", err);
        contentDiv.innerHTML = `<div class="alert alert-danger">
            <i class="bi bi-exclamation-triangle"></i> Failed to render file.<br>
            <small>${err.message}</small><br>
            <button class="btn btn-sm btn-light mt-2" onclick="downloadFile(${id})">Try Downloading</button>
        </div>`;
    }

    // Cleanup
    modalEl.addEventListener('hidden.bs.modal', () => {
        contentDiv.innerHTML = '<div class="text-dark">Loading...</div>';
        // Reset modal size when closed
        const dialog = document.getElementById('viewModalDialog');
        dialog.classList.remove('modal-fullscreen');
        dialog.classList.add('modal-xl');
        const icon = document.querySelector('#resizeModalBtn i');
        if (icon) {
            icon.className = 'bi bi-arrows-fullscreen';
        }
    }, { once: true });
}

// Resize Modal Handler
function setupResizeHandler() {
    const btn = document.getElementById('resizeModalBtn');
    if (!btn) return;

    btn.addEventListener('click', function () {
        const dialog = document.getElementById('viewModalDialog');
        const icon = this.querySelector('i');

        if (dialog.classList.contains('modal-xl')) {
            dialog.classList.remove('modal-xl');
            dialog.classList.add('modal-fullscreen');
            icon.className = 'bi bi-fullscreen-exit';
            this.title = "Exit Fullscreen";
        } else {
            dialog.classList.remove('modal-fullscreen');
            dialog.classList.add('modal-xl');
            icon.className = 'bi bi-arrows-fullscreen';
            this.title = "Toggle Fullscreen";
        }
    });
}

// Upload Handler
document.getElementById('uploadForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);

    try {
        await API.uploadEvidence(token, caseId, formData);
        const modal = bootstrap.Modal.getInstance(document.getElementById('uploadModal'));
        modal.hide();
        e.target.reset();
        showAlert('success', 'File uploaded, hashed, and encrypted successfully.');
        loadEvidence();
    } catch (err) {
        showAlert('danger', err.message);
    }
});

async function downloadFile(id) {
    try {
        await API.downloadEvidence(token, id);
    } catch (err) {
        showAlert('danger', "Download failed");
    }
}

function showAlert(type, msg) {
    const ph = document.getElementById('alertPlaceholder');
    ph.innerHTML = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${msg}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    setTimeout(() => {
        ph.innerHTML = '';
    }, 5000);
}

// Financial Module Logic
let financialEntitiesMap = {}; // Id -> Entity Object

async function loadFinancialData() {
    try {
        const entities = await API.getFinancialEntities(token, caseId);

        if (entities.length > 0) {
            document.getElementById('financialCard').classList.remove('d-none');
            const listDiv = document.getElementById('financialEntitiesList');
            const selectDiv = document.getElementById('npciEntitySelect');

            listDiv.innerHTML = '';
            selectDiv.innerHTML = '';
            financialEntitiesMap = {};

            entities.forEach(ent => {
                financialEntitiesMap[ent.id] = ent;

                // Add to List
                const identifier = ent.upi_id || ent.account_number || ent.wallet_provider;
                const item = document.createElement('div');
                item.className = 'd-flex justify-content-between align-items-center mb-2 p-2 bg-light rounded border';
                item.innerHTML = `
                    <div>
                        <span class="badge bg-dark me-2">${ent.entity_type.replace('_', ' ').toUpperCase()}</span>
                        <span class="font-monospace fw-bold">${identifier}</span>
                    </div>
                `;
                listDiv.appendChild(item);

                // Add to Modal Select
                const option = document.createElement('option');
                option.value = ent.id;
                option.textContent = `${ent.entity_type.toUpperCase()}: ${identifier}`;
                selectDiv.appendChild(option);
            });
        }
    } catch (err) {
        console.error("Financial Data Error:", err);
    }
}

// NPCI Form Handler
const npciForm = document.getElementById('npciForm');
if (npciForm) {
    npciForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const data = Object.fromEntries(formData.entries());

        const entityId = parseInt(data.financial_entity_id);
        const entity = financialEntitiesMap[entityId];

        if (!entity) {
            showAlert('danger', 'Invalid Entity Selected');
            return;
        }

        const identifier = entity.upi_id || entity.account_number || "N/A";

        try {
            await API.createNPCIRequest(token, caseId, {
                financial_entity_id: entityId,
                request_type: data.request_type,
                reason: data.reason,
                upi_id: identifier
            });

            showAlert('success', 'NPCI/Bank Request Initiated Successfully');
            bootstrap.Modal.getInstance(document.getElementById('npciModal')).hide();
            e.target.reset();
        } catch (err) {
            showAlert('danger', err.message);
        }
    });
}
// Enhance Init to load financial data
const originalInit = init;
init = async function () {
    await originalInit(); // Call original init
    await loadFinancialData(); // Then load financial data
};

setupResizeHandler();
init();
