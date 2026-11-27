const token = localStorage.getItem('token');
const urlParams = new URLSearchParams(window.location.search);
const caseId = urlParams.get('id');

if (!token || !caseId) {
    window.location.href = 'dashboard.html';
}

// Global scope for button logic
let userRole = null;
let cachedCaseInfo = null;
let cachedEvidenceList = [];
let cachedFinancialEntities = [];
let cachedFreezeRequests = [];
let cachedTimeline = { timeline: [] };

document.getElementById('logoutBtn')?.addEventListener('click', async () => {
    await API.logout(token);
    localStorage.removeItem('token');
    window.location.href = 'index.html';
});

document.getElementById('exportBsa63Btn')?.addEventListener('click', async () => {
    try {
        const manifest = await API.getBsa63Manifest(token, caseId);
        const blob = new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `BSA63_Manifest_Case_${caseId}.json`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        showAlert('success', `Exported Sec 63(4)(c) BSA manifest (${manifest.total_evidence_items} hashed evidence item(s)).`);
    } catch (err) {
        showAlert('danger', err.message || 'Failed to export Section 63 BSA manifest');
    }
});

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
        cachedCaseInfo = caseInfo;
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
        if (typeof showToast === 'function') {
            showToast("Failed to load case data", "danger");
        }
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
        cachedEvidenceList = evidenceList;
        const tbody = document.getElementById('evidenceTableBody');
        tbody.innerHTML = '';

        if (evidenceList.length === 0) {
            document.getElementById('noEvidenceMsg').classList.remove('d-none');
            return;
        }
        document.getElementById('noEvidenceMsg').classList.add('d-none');

        evidenceList.forEach(e => {
            const tr = document.createElement('tr');

            const tdName = document.createElement('td');
            tdName.textContent = e.original_filename;

            const tdType = document.createElement('td');
            const typeBadge = document.createElement('span');
            typeBadge.className = 'badge bg-info text-dark';
            typeBadge.textContent = e.file_type;
            tdType.appendChild(typeBadge);

            const tdHash = document.createElement('td');
            const codeEl = document.createElement('code');
            codeEl.title = e.file_hash;
            codeEl.textContent = `${e.file_hash.substring(0, 8)}...`;
            tdHash.appendChild(codeEl);

            const tdView = document.createElement('td');
            tdView.className = 'text-center';
            const viewBtn = document.createElement('button');
            viewBtn.className = 'btn btn-sm btn-outline-primary';
            viewBtn.innerHTML = '<i class="bi bi-eye"></i> View';
            viewBtn.addEventListener('click', () => viewEvidence(e.id, e.original_filename, e.file_hash));
            tdView.appendChild(viewBtn);

            const tdDownload = document.createElement('td');
            tdDownload.className = 'text-end pe-3';
            const dlBtn = document.createElement('button');
            dlBtn.className = 'btn btn-sm btn-outline-secondary';
            dlBtn.innerHTML = '<i class="bi bi-download"></i> Download';
            dlBtn.addEventListener('click', () => downloadFile(e.id));
            tdDownload.appendChild(dlBtn);

            tr.append(tdName, tdType, tdHash, tdView, tdDownload);
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

    const viewUrl = `${API_URL}/files/view/${id}`;
    const ext = filename.split('.').pop().toLowerCase();
    let activeBlobUrl = null;

    async function fetchAuthenticatedResponse(url) {
        const resp = await fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!resp.ok) {
            throw new Error(`Failed to fetch evidence (${resp.status})`);
        }
        return resp;
    }

    try {
        // 1. Images
        if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'].includes(ext)) {
            const resp = await fetchAuthenticatedResponse(viewUrl);
            const blob = await resp.blob();
            activeBlobUrl = URL.createObjectURL(blob);
            contentDiv.innerHTML = '';
            const img = document.createElement('img');
            img.src = activeBlobUrl;
            img.className = 'img-fluid rounded';
            img.style.maxHeight = '70vh';
            img.style.objectFit = 'contain';
            contentDiv.appendChild(img);
        }

        // 2. Video
        else if (['mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv'].includes(ext)) {
            const resp = await fetchAuthenticatedResponse(viewUrl);
            const blob = await resp.blob();
            activeBlobUrl = URL.createObjectURL(blob);
            contentDiv.innerHTML = '';
            const video = document.createElement('video');
            video.controls = true;
            video.autoplay = true;
            video.className = 'w-100';
            video.style.maxHeight = '70vh';
            video.src = activeBlobUrl;
            contentDiv.appendChild(video);
        }

        // 3. Audio
        else if (['mp3', 'wav', 'ogg', 'm4a'].includes(ext)) {
            const resp = await fetchAuthenticatedResponse(viewUrl);
            const blob = await resp.blob();
            activeBlobUrl = URL.createObjectURL(blob);
            contentDiv.innerHTML = `
                <div class="text-center p-5">
                    <i class="bi bi-file-music-fill fs-1 text-info animate-pulse mb-3 d-block"></i>
                </div>`;
            const audio = document.createElement('audio');
            audio.controls = true;
            audio.autoplay = true;
            audio.className = 'w-100';
            audio.style.maxWidth = '500px';
            audio.src = activeBlobUrl;
            contentDiv.querySelector('div').appendChild(audio);
        }

        // 4. PDF
        else if (ext === 'pdf') {
            const resp = await fetchAuthenticatedResponse(viewUrl);
            const blob = await resp.blob();
            activeBlobUrl = URL.createObjectURL(blob);
            contentDiv.innerHTML = '';
            const iframe = document.createElement('iframe');
            iframe.src = activeBlobUrl;
            iframe.width = '100%';
            iframe.height = '700px';
            iframe.style.border = 'none';
            iframe.style.borderRadius = '8px';
            contentDiv.appendChild(iframe);
        }

        // 5. Spreadsheets (XSLX, CSV, ODTS) -> SheetJS + DOMPurify
        else if (['xlsx', 'xls', 'csv', 'ods'].includes(ext)) {
            if (typeof XLSX === 'undefined') {
                throw new Error("SheetJS library (XLSX) is not loaded. Please check your internet connection.");
            }
            const resp = await fetchAuthenticatedResponse(viewUrl);
            const blob = await resp.blob();
            const buffer = await blob.arrayBuffer();

            try {
                const wb = XLSX.read(buffer, { type: 'array' });
                if (!wb.SheetNames || wb.SheetNames.length === 0) {
                    throw new Error("Spreadsheet contains no sheets.");
                }
                const ws = wb.Sheets[wb.SheetNames[0]];
                const tblHtml = XLSX.utils.sheet_to_html(ws, { id: "excelTable", className: "table table-striped table-bordered table-sm" });
                contentDiv.innerHTML = `<div class="bg-white p-2 rounded border" style="max-height: 70vh; overflow: auto; text-align: left;">${safeHTML(tblHtml)}</div>`;
            } catch (e) {
                console.error("SheetJS Error:", e);
                throw new Error("Failed to parse spreadsheet: " + e.message);
            }
        }

        // 6. Documents (DOCX) -> Mammoth + DOMPurify
        else if (ext === 'docx') {
            const resp = await fetchAuthenticatedResponse(viewUrl);
            const blob = await resp.blob();
            const arrayBuffer = await blob.arrayBuffer();

            const result = await mammoth.convertToHtml({ arrayBuffer: arrayBuffer });
            contentDiv.innerHTML = `<div class="bg-white text-dark p-4 rounded text-start" style="max-height: 70vh; overflow: auto;">${safeHTML(result.value)}</div>`;
        }

        // 7. Text / Logs
        else if (['txt', 'log', 'json', 'xml', 'py', 'js', 'md'].includes(ext)) {
            const resp = await fetchAuthenticatedResponse(viewUrl);
            const text = await resp.text();
            contentDiv.innerHTML = '';
            const pre = document.createElement('pre');
            pre.className = 'text-start text-dark bg-light p-3 rounded border';
            pre.style.maxHeight = '70vh';
            pre.style.overflow = 'auto';
            pre.style.fontFamily = 'monospace';
            pre.textContent = text;
            contentDiv.appendChild(pre);
        }

        // 8. Archives (ZIP) -> JSZip
        else if (ext === 'zip') {
            const resp = await fetchAuthenticatedResponse(viewUrl);
            const blob = await resp.blob();
            const zip = await JSZip.loadAsync(blob);

            const wrapper = document.createElement('div');
            wrapper.className = 'p-3';
            wrapper.style.maxHeight = '70vh';
            wrapper.style.overflow = 'auto';

            const heading = document.createElement('h6');
            heading.className = 'text-info mb-3';
            heading.innerHTML = '<i class="bi bi-file-zip-fill"></i> Archive Contents';
            wrapper.appendChild(heading);

            const ul = document.createElement('ul');
            ul.className = 'list-group list-group-flush text-start';
            zip.forEach((relativePath, zipEntry) => {
                const li = document.createElement('li');
                li.className = 'list-group-item bg-transparent text-dark border-secondary';
                const icon = document.createElement('i');
                icon.className = `bi ${zipEntry.dir ? 'bi-folder-fill text-warning' : 'bi-file-earmark-text text-light'} me-2`;
                li.appendChild(icon);
                li.appendChild(document.createTextNode(relativePath));
                ul.appendChild(li);
            });
            wrapper.appendChild(ul);
            contentDiv.innerHTML = '';
            contentDiv.appendChild(wrapper);
        }

        // Fallback
        else {
            contentDiv.innerHTML = `<div class="text-dark p-5">
                <i class="bi bi-file-earmark-binary fs-1 opacity-50"></i>
                <p class="mt-3">Preview not available for this file type (${escapeHtml(ext)}).</p>
                <button class="btn btn-primary btn-sm mt-2" id="fallbackDownloadBtn">Download to View</button>
            </div>`;
            contentDiv.querySelector('#fallbackDownloadBtn').addEventListener('click', () => downloadFile(id));
        }

    } catch (err) {
        console.error("Viewer Error:", err);
        contentDiv.innerHTML = `<div class="alert alert-danger">
            <i class="bi bi-exclamation-triangle"></i> Failed to render file.<br>
            <small class="viewer-err-msg"></small><br>
            <button class="btn btn-sm btn-light mt-2" id="errDownloadBtn">Try Downloading</button>
        </div>`;
        contentDiv.querySelector('.viewer-err-msg').textContent = err.message;
        contentDiv.querySelector('#errDownloadBtn').addEventListener('click', () => downloadFile(id));
    }

    // Cleanup
    modalEl.addEventListener('hidden.bs.modal', () => {
        if (activeBlobUrl) {
            URL.revokeObjectURL(activeBlobUrl);
            activeBlobUrl = null;
        }
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
    if (typeof showToast === 'function') {
        showToast(msg, type);
    }
    const ph = document.getElementById('alertPlaceholder');
    if (!ph) return;
    ph.innerHTML = '';
    const alertDiv = document.createElement('div');
    const allowed = ['primary', 'secondary', 'success', 'danger', 'warning', 'info', 'dark'];
    const safeType = allowed.includes(type) ? type : 'info';
    alertDiv.className = `alert alert-${safeType} alert-dismissible fade show`;
    alertDiv.setAttribute('role', 'alert');
    alertDiv.appendChild(document.createTextNode(String(msg ?? '')));
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn-close';
    closeBtn.setAttribute('data-bs-dismiss', 'alert');
    alertDiv.appendChild(closeBtn);
    ph.appendChild(alertDiv);
    setTimeout(() => {
        ph.innerHTML = '';
    }, 5000);
}

// Financial Module Logic
let financialEntitiesMap = {}; // Id -> Entity Object

async function loadFinancialData() {
    try {
        const [entities, timelineData] = await Promise.all([
            API.getFinancialEntities(token, caseId),
            API.getCaseTimeline(token, caseId).catch(() => ({ timeline: [] })),
        ]);
        cachedFinancialEntities = entities;
        cachedTimeline = timelineData;

        if (entities.length > 0) {
            document.getElementById('financialCard').classList.remove('d-none');
            const listDiv = document.getElementById('financialEntitiesList');
            const selectDiv = document.getElementById('npciEntitySelect');
            const freezeSelectDiv = document.getElementById('freezeEntitySelect');

            listDiv.innerHTML = '';
            if (selectDiv) selectDiv.innerHTML = '';
            if (freezeSelectDiv) freezeSelectDiv.innerHTML = '';
            financialEntitiesMap = {};

            entities.forEach(ent => {
                financialEntitiesMap[ent.id] = ent;

                // Add to List safely
                const identifier = ent.upi_id || ent.account_number || ent.wallet_provider || 'N/A';
                const item = document.createElement('div');
                item.className = 'd-flex justify-content-between align-items-center mb-2 p-2 bg-light rounded border';

                const inner = document.createElement('div');
                const badge = document.createElement('span');
                badge.className = 'badge bg-dark me-2';
                badge.textContent = ent.entity_type.replace('_', ' ').toUpperCase();

                const identSpan = document.createElement('span');
                identSpan.className = 'font-monospace fw-bold';
                identSpan.textContent = identifier;

                inner.append(badge, identSpan);
                item.appendChild(inner);
                listDiv.appendChild(item);

                // Add to NPCI Modal Select
                if (selectDiv) {
                    const option = document.createElement('option');
                    option.value = ent.id;
                    option.textContent = `${ent.entity_type.toUpperCase()}: ${identifier}`;
                    selectDiv.appendChild(option);
                }

                // Add to Freeze Modal Select
                if (freezeSelectDiv) {
                    const fOpt = document.createElement('option');
                    fOpt.value = ent.id;
                    fOpt.textContent = `${ent.entity_type.toUpperCase()}: ${identifier}`;
                    freezeSelectDiv.appendChild(fOpt);
                }
            });

            prefillFreezeInputs(entities[0]);
            await loadFreezeRequests();
        }
        renderGoldenHourSummary(cachedCaseInfo, cachedFinancialEntities, cachedFreezeRequests, cachedTimeline);
    } catch (err) {
        console.error("Financial Data Error:", err);
    }
}

function prefillFreezeInputs(ent) {
    if (!ent) return;
    const bankInput = document.getElementById('freezeBankName');
    const accInput = document.getElementById('freezeAccountNumber');
    if (bankInput) bankInput.value = ent.bank_name || ent.wallet_provider || 'PSP / Partner Bank';
    if (accInput) accInput.value = ent.account_number || ent.upi_id || '';
}

document.getElementById('freezeEntitySelect')?.addEventListener('change', (e) => {
    const ent = financialEntitiesMap[parseInt(e.target.value, 10)];
    prefillFreezeInputs(ent);
});

async function loadFreezeRequests() {
    const listDiv = document.getElementById('freezeRequestsList');
    if (!listDiv) return;
    try {
        const allReqs = await API.getFreezeRequests(token);
        const caseReqs = allReqs.filter(r => String(r.case_id) === String(caseId));
        cachedFreezeRequests = caseReqs;
        listDiv.innerHTML = '';
        if (caseReqs.length === 0) return;

        const heading = document.createElement('h6');
        heading.className = 'text-muted small fw-bold mt-2 mb-2';
        heading.textContent = `ACTIVE FREEZE ORDERS (${caseReqs.length})`;
        listDiv.appendChild(heading);

        caseReqs.forEach(req => {
            const row = document.createElement('div');
            row.className = 'd-flex justify-content-between align-items-center p-2 mb-1 bg-light rounded border small';

            const left = document.createElement('div');
            const bankStrong = document.createElement('strong');
            bankStrong.textContent = `${req.bank_name} `;
            const accSpan = document.createElement('span');
            accSpan.className = 'font-monospace text-muted';
            accSpan.textContent = req.account_number;
            left.append(bankStrong, accSpan);

            const badge = document.createElement('span');
            badge.className = `badge ${req.status === 'confirmed' ? 'bg-success' : 'bg-danger'}`;
            badge.textContent = `${String(req.urgency_level || '').toUpperCase()} · ${String(req.status || '').toUpperCase()}`;

            row.append(left, badge);
            listDiv.appendChild(row);
        });
    } catch (_err) {
        // Non-blocking
    }
}

document.getElementById('freezeForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());
    const entityId = parseInt(data.financial_entity_id, 10);

    try {
        await API.createFreezeRequest(token, caseId, {
            financial_entity_id: entityId,
            bank_name: data.bank_name.trim(),
            account_number: data.account_number.trim(),
            urgency_level: data.urgency_level,
            justification: data.justification.trim()
        });
        showAlert('success', 'Section 106 BNSS Freeze Order issued successfully.');
        bootstrap.Modal.getInstance(document.getElementById('freezeModal'))?.hide();
        await loadFreezeRequests();
    } catch (err) {
        showAlert('danger', err.message || 'Failed to issue freeze order');
    }
});

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
// NCRP / 1930 Golden Hour Money-Trail & Lien Summary Card
function renderGoldenHourSummary(caseInfo, entities, freezeReqs, timelineData) {
    const card = document.getElementById('goldenHourCard');
    if (!card) return;
    const events = (timelineData && timelineData.timeline) || [];
    const caseAmt = parseFloat(caseInfo?.amount_involved || '0') || 0;

    if (entities.length === 0 && events.length === 0 && caseAmt <= 0) {
        card.classList.add('d-none');
        return;
    }
    card.classList.remove('d-none');

    const toNum = (v) => {
        const n = parseFloat(String(v || '0').replace(/[^\d.]/g, ''));
        return Number.isFinite(n) ? n : 0;
    };
    const fmtINR = (n) => `₹${Math.round(n).toLocaleString('en-IN')}`;

    const paymentSum = events
        .filter(ev => ['payment', 'complaint_filed'].includes(String(ev.event_type || '').toLowerCase()))
        .reduce((acc, ev) => acc + toNum(ev.amount), 0);
    const entitySum = entities.reduce((acc, ent) => acc + toNum(ent.transaction_amount), 0);
    const defrauded = Math.max(caseAmt, paymentSum, entitySum);

    const hopTracedSum = events
        .filter(ev => ['transfer', 'withdrawal'].includes(String(ev.event_type || '').toLowerCase()))
        .reduce((acc, ev) => acc + toNum(ev.amount), 0);
    const traced = Math.max(entitySum, hopTracedSum);

    const frozenEntityIds = new Set(
        freezeReqs
            .filter(r => ['generated', 'sent', 'confirmed'].includes(String(r.status || '').toLowerCase()))
            .map(r => r.financial_entity_id)
    );
    const frozen = entities
        .filter(ent => frozenEntityIds.has(ent.id))
        .reduce((acc, ent) => acc + toNum(ent.transaction_amount), 0);
    const atRisk = Math.max(0, defrauded - frozen);

    document.getElementById('ghDefrauded').textContent = fmtINR(defrauded);
    document.getElementById('ghTraced').textContent = fmtINR(traced);
    document.getElementById('ghFrozen').textContent = fmtINR(frozen);
    document.getElementById('ghAtRisk').textContent = fmtINR(atRisk);

    const statusBadge = document.getElementById('goldenHourStatusBadge');
    if (statusBadge) {
        statusBadge.textContent = frozen > 0 ? 'Lien Active (Sec 106 BNSS)' : 'Action Required (Unfrozen)';
        statusBadge.className = frozen > 0 ? 'badge bg-success text-white' : 'badge bg-warning text-dark';
    }

    const trailDiv = document.getElementById('goldenHourHopTrail');
    if (trailDiv) {
        trailDiv.innerHTML = '';
        const label = document.createElement('span');
        label.className = 'fw-bold text-muted me-1';
        label.textContent = 'CFCFRMS Hop Trail:';
        trailDiv.appendChild(label);

        entities.forEach((ent, idx) => {
            if (idx > 0) {
                const arrow = document.createElement('i');
                arrow.className = 'bi bi-arrow-right text-muted';
                trailDiv.appendChild(arrow);
            }
            const layerTag = idx === 0 ? 'Layer-1' : `Layer-${idx + 1}`;
            const isFrozen = frozenEntityIds.has(ent.id);
            const ident = ent.account_number || ent.upi_id || ent.wallet_provider || `Entity #${ent.id}`;
            const amtText = toNum(ent.transaction_amount) > 0 ? ` (${fmtINR(toNum(ent.transaction_amount))})` : '';

            const pill = document.createElement('span');
            pill.className = `badge ${isFrozen ? 'bg-success' : 'bg-warning text-dark'} px-2 py-1`;
            pill.textContent = `${layerTag}: ${ident}${amtText} · ${isFrozen ? 'LIEN-MARKED' : 'AT-RISK'}`;
            trailDiv.appendChild(pill);
        });
    }
}

// One-Click IO Case Investigation Brief PDF Export
document.getElementById('exportCaseBriefBtn')?.addEventListener('click', async () => {
    try {
        if (!window.jspdf || !window.jspdf.jsPDF) {
            window.print();
            return;
        }
        const { jsPDF } = window.jspdf;
        const doc = new jsPDF();
        const c = cachedCaseInfo || {};
        const reqs = await API.getCaseRequests(token, caseId).catch(() => []);
        const manifest = await API.getBsa63Manifest(token, caseId).catch(() => ({ evidence_items: [] }));

        doc.setFillColor(13, 110, 253);
        doc.rect(0, 0, 210, 20, 'F');
        doc.setTextColor(255, 255, 255);
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(14);
        doc.text('N.E.T.R.A. — IO CASE INVESTIGATION BRIEF', 105, 13, { align: 'center' });

        doc.setTextColor(0, 0, 0);
        doc.setFontSize(10);
        doc.setFont('helvetica', 'normal');
        doc.text(`Generated: ${new Date().toLocaleString()} | FIR: ${c.fir_number || caseId}`, 14, 28);
        doc.text(`Station: ${c.police_station || '-'} | Type: ${c.case_type || '-'} | Status: ${(c.status || '-').toUpperCase()}`, 14, 34);

        let y = 42;
        doc.autoTable({
            startY: y,
            head: [['Defrauded Inflow', 'Traced (L1/L2)', 'Frozen (Sec 106 BNSS)', 'At-Risk Balance']],
            body: [[
                document.getElementById('ghDefrauded')?.textContent || '₹0',
                document.getElementById('ghTraced')?.textContent || '₹0',
                document.getElementById('ghFrozen')?.textContent || '₹0',
                document.getElementById('ghAtRisk')?.textContent || '₹0',
            ]],
            theme: 'grid',
            headStyles: { fillColor: [33, 37, 41] },
            styles: { fontSize: 9 },
        });
        y = doc.lastAutoTable.finalY + 8;

        if (cachedFinancialEntities.length > 0) {
            doc.setFont('helvetica', 'bold');
            doc.text('Linked Suspect / Mule Financial Entities', 14, y);
            y += 3;
            doc.autoTable({
                startY: y,
                head: [['Type', 'Bank / PSP', 'Account / UPI ID', 'Amount', 'Status']],
                body: cachedFinancialEntities.map(e => [
                    e.entity_type || '-',
                    e.bank_name || e.wallet_provider || '-',
                    e.account_number || e.upi_id || '-',
                    e.transaction_amount || '0',
                    e.verification_status || '-',
                ]),
                theme: 'striped',
                styles: { fontSize: 8 },
            });
            y = doc.lastAutoTable.finalY + 8;
        }

        if (reqs.length > 0 || cachedFreezeRequests.length > 0) {
            doc.setFont('helvetica', 'bold');
            doc.text('Section 94 & Section 106 BNSS Requisitions / Freeze Orders', 14, y);
            y += 3;
            const reqRows = [
                ...reqs.map(r => ['Sec 94 BNSS', r.request_type, r.mobile_number, r.status]),
                ...cachedFreezeRequests.map(f => ['Sec 106 BNSS Freeze', f.bank_name, f.account_number, f.status]),
            ];
            doc.autoTable({
                startY: y,
                head: [['Legal Provision', 'Target / Type', 'Identifier', 'Status']],
                body: reqRows,
                theme: 'striped',
                styles: { fontSize: 8 },
            });
            y = doc.lastAutoTable.finalY + 8;
        }

        const evItems = manifest.evidence_items || cachedEvidenceList || [];
        doc.setFont('helvetica', 'bold');
        doc.text(`Section 63 BSA, 2023 Evidence Hash Manifest (${evItems.length} item(s))`, 14, y);
        y += 3;
        doc.autoTable({
            startY: y,
            head: [['Filename', 'Type', 'SHA-256 Digest', 'Status']],
            body: evItems.length > 0
                ? evItems.map(ev => [ev.original_filename || '-', ev.file_type || '-', ev.file_hash || '-', ev.verification_status || '-'])
                : [['No evidence files uploaded yet', '-', '-', '-']],
            theme: 'grid',
            styles: { fontSize: 7 },
        });

        const safeFir = String(c.fir_number || caseId).replace(/[^\w.-]+/g, '_');
        doc.save(`NETRA_Case_Brief_${safeFir}.pdf`);
        showToast('Exported IO Case Investigation Brief PDF.', 'success');
    } catch (err) {
        showToast(err.message || 'Failed to export Case Brief', 'danger');
    }
});

// Enhance Init to load financial data
const originalInit = init;
init = async function () {
    await originalInit(); // Call original init
    await loadFinancialData(); // Then load financial data
};

setupResizeHandler();
init();
