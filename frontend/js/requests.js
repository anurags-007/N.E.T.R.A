let currentUser = null;
let allRequests = []; // Cache for requests
let allCases = []; // Cache for cases

// Logout
document.getElementById('logoutBtn')?.addEventListener('click', async () => {
    await API.logout();
    window.location.href = 'index.html';
});

// Service Worker, Sidebar, Theme & Filter bindings (strict CSP - external JS)
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/frontend/sw.js').catch(() => {});
}
const sidebarEl = document.querySelector('.sidebar');
const toggleBtn = document.getElementById('sidebarToggle');
if (toggleBtn && sidebarEl) {
    toggleBtn.addEventListener('click', (e) => { e.stopPropagation(); sidebarEl.classList.toggle('active'); });
    document.addEventListener('click', (e) => {
        if (window.innerWidth <= 768 && sidebarEl.classList.contains('active') && !sidebarEl.contains(e.target) && e.target !== toggleBtn) {
            sidebarEl.classList.remove('active');
        }
    });
}
const darkModeBtn = document.getElementById('darkModeToggle');
if (localStorage.getItem('theme') === 'dark') {
    document.body.classList.add('dark-mode');
    if (darkModeBtn) darkModeBtn.innerHTML = '<i class="bi bi-sun-fill"></i>';
}
darkModeBtn?.addEventListener('click', () => {
    document.body.classList.toggle('dark-mode');
    const isDark = document.body.classList.contains('dark-mode');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
    darkModeBtn.innerHTML = isDark ? '<i class="bi bi-sun-fill"></i>' : '<i class="bi bi-moon-stars"></i>';
});

document.getElementById('requestSearchInput')?.addEventListener('keyup', () => filterRequests());
document.getElementById('requestStatusFilter')?.addEventListener('change', () => filterRequests());
document.getElementById('requestTypeFilter')?.addEventListener('change', () => filterRequests());
document.getElementById('requestSortBy')?.addEventListener('change', () => filterRequests());
document.getElementById('clearRequestFiltersBtn')?.addEventListener('click', () => clearRequestFilters());
document.getElementById('rejectReviewBtn')?.addEventListener('click', () => {
    const reason = prompt("Enter Rejection Reason:");
    if (reason) submitReview('reject', reason);
});
document.getElementById('approveReviewBtn')?.addEventListener('click', () => submitReview('approve'));
document.getElementById('emailTemplate')?.addEventListener('change', () => applyTemplate());
document.getElementById('mailtoLink')?.addEventListener('click', () => setTimeout(() => enableMarkSent(), 2000));
document.getElementById('copyEmailBtn')?.addEventListener('click', () => copyEmailToClipboard());
document.getElementById('markSentBtn')?.addEventListener('click', () => markRequestAsSent());

async function init() {
    try {
        currentUser = await API.getMe();

        // Fix Profile Display
        document.getElementById('userNameDisplay').textContent = currentUser.username;
        const roleDisplay = document.getElementById('userRoleDisplay');
        if (roleDisplay) {
            roleDisplay.textContent = (currentUser.rank || currentUser.role).toUpperCase();
        }
        if (typeof setRoleBasedNav === 'function') setRoleBasedNav(currentUser.role);

        loadRequests();
        loadCasesForSelect();

    } catch (err) {
        console.error(err);
        window.location.href = 'index.html';
    }
}

async function loadRequests() {
    try {
        allRequests = await API.getRequests(); // Store in cache
        filterRequests(); // Initial Render
    } catch (err) {
        console.error(err);
        showAlert('danger', 'Failed to load requests');
    }
}

function getStatusColor(status) {
    switch (status) {
        case 'pending': return 'warning';
        case 'approved': return 'success';
        case 'dispatched': return 'info';
        case 'rejected': return 'danger';
        default: return 'secondary';
    }
}

// Filter & Sort Logic
function filterRequests() {
    const searchTerm = document.getElementById('requestSearchInput').value.toLowerCase();
    const statusFilter = document.getElementById('requestStatusFilter').value;
    const typeFilter = document.getElementById('requestTypeFilter').value;
    const sortBy = document.getElementById('requestSortBy').value;

    let filtered = allRequests.filter(r => {
        const matchesSearch =
            r.id.toString().includes(searchTerm) ||
            r.mobile_number.toLowerCase().includes(searchTerm) ||
            r.case_id.toString().includes(searchTerm) ||
            (r.rejection_reason && r.rejection_reason.toLowerCase().includes(searchTerm));

        const matchesStatus = statusFilter === '' || r.status === statusFilter;
        const matchesType = typeFilter === '' || r.request_type === typeFilter;

        return matchesSearch && matchesStatus && matchesType;
    });

    // Sorting
    filtered.sort((a, b) => {
        if (sortBy === 'date_desc') return new Date(b.created_at) - new Date(a.created_at);
        if (sortBy === 'date_asc') return new Date(a.created_at) - new Date(b.created_at);
        if (sortBy === 'id_desc') return b.id - a.id;
        if (sortBy === 'id_asc') return a.id - b.id;
        return 0;
    });

    renderRequestsTable(filtered);
}

function clearRequestFilters() {
    document.getElementById('requestSearchInput').value = '';
    document.getElementById('requestStatusFilter').value = '';
    document.getElementById('requestTypeFilter').value = '';
    document.getElementById('requestSortBy').value = 'date_desc';
    filterRequests();
}

function renderRequestsTable(requests) {
    const tbody = document.getElementById('requestsTableBody');
    tbody.innerHTML = '';

    document.getElementById('requestResultCount').innerText = requests.length;
    document.getElementById('requestTotalCount').innerText = allRequests.length;

    if (requests.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">No requests found matching criteria</td></tr>`;
        return;
    }

    requests.forEach(r => {
        const tr = document.createElement('tr');
        const isAuthorized = ['sho', 'admin', 'dy_sp', 'sp', 'dig', 'igp', 'dgp'].includes(currentUser.role);

        // Calculate Pending Days
        const createdDate = new Date(r.created_at);
        const now = new Date();
        const diffDays = Math.ceil(Math.abs(now - createdDate) / (1000 * 60 * 60 * 24));

        let statusBadge = `<span class="badge bg-${getStatusColor(r.status)}">${escapeHtml(r.status.toUpperCase())}</span>`;
        if (r.status === 'pending' && diffDays > 7) {
            statusBadge += ` <span class="badge bg-danger ms-1" title="Escalation Required"><i class="bi bi-clock-history"></i> ${diffDays}d</span>`;
        }

        const linkedCase = allCases.find(c => c.id === r.case_id);
        const caseDisplay = linkedCase ? `${linkedCase.fir_number}` : `Case #${r.case_id}`;

        tr.innerHTML = safeHTML(`
            <td>#${escapeHtml(String(r.id))}</td>
            <td><span class="badge bg-light text-dark border">${escapeHtml(caseDisplay)}</span></td>
            <td class="font-monospace">${escapeHtml(r.mobile_number)}</td>
            <td>${escapeHtml(r.request_type)}</td>
            <td>${statusBadge}</td>
            <td><small class="text-muted text-truncate d-inline-block" style="max-width: 150px;">${escapeHtml(r.rejection_reason || r.reason || '')}</small></td>
            <td class="req-actions-cell"></td>
        `);

        const actCell = tr.querySelector('.req-actions-cell');
        if (isAuthorized && r.status === 'pending') {
            const revBtn = document.createElement('button');
            revBtn.className = 'btn btn-sm btn-success';
            revBtn.textContent = 'Review';
            revBtn.addEventListener('click', () => openReview(r.id));
            actCell.appendChild(revBtn);
        } else if (r.status === 'approved') {
            const upBtn = document.createElement('button');
            upBtn.className = 'btn btn-sm btn-outline-secondary me-1';
            upBtn.innerHTML = '<i class="bi bi-upload"></i> Upload Signed / Reply';
            upBtn.addEventListener('click', () => uploadSignedCopy(r.id));
            const emBtn = document.createElement('button');
            emBtn.className = 'btn btn-sm btn-outline-dark';
            emBtn.innerHTML = '<i class="bi bi-envelope-at"></i> Email Draft';
            emBtn.addEventListener('click', () => generateEmailDraft(r.id));
            actCell.append(upBtn, emBtn);
        } else if (r.status === 'dispatched') {
            const upBtn = document.createElement('button');
            upBtn.className = 'btn btn-sm btn-outline-secondary me-1';
            upBtn.innerHTML = '<i class="bi bi-upload"></i> Upload Reply';
            upBtn.addEventListener('click', () => uploadSignedCopy(r.id));
            const sentBtn = document.createElement('button');
            sentBtn.className = 'btn btn-sm btn-success disabled';
            sentBtn.innerHTML = '<i class="bi bi-check2-all"></i> Sent';
            actCell.append(upBtn, sentBtn);
        }

        tbody.appendChild(tr);
    });
}

async function loadCasesForSelect() {
    try {
        allCases = await API.getCases(); // Cache cases
        const select = document.getElementById('caseSelect');
        // Reset and add placeholder
        select.innerHTML = '<option value="" disabled selected>Select Investigation Case</option>';

        allCases.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.innerText = `${c.fir_number} - ${c.police_station}`;
            select.appendChild(opt);
        });

        // Re-render requests if they loaded before cases, to update Linked Case column
        if (allRequests.length > 0) filterRequests();

    } catch (err) {
        console.error("Could not load cases for select");
    }
}

// Legal Presets Logic
const JUSTIFICATION_TEMPLATES = {
    'BNSS_94': 'In exercise of the powers conferred under Section 94 of the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023, the requested data is required for the purpose of ongoing investigation in the linked case to establish identity and trace suspects.',
    'BNSS_106': 'Seeking seizure/freeze action under Section 106 of the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023 regarding property/digital records suspected to be involved in the commission of the offence.',
    'EMERGENCY': 'URGENT: Request initiated due to a life-threatening emergency situation. Official written requisition will be provided ex-post facto as per department protocol.',
    'OTHER': ''
};

document.getElementById('legalPreset')?.addEventListener('change', (e) => {
    const preset = e.target.value;
    const textarea = document.getElementById('legalReason');
    if (textarea && JUSTIFICATION_TEMPLATES[preset]) {
        textarea.value = JUSTIFICATION_TEMPLATES[preset];
    }
});

// Create Request
document.getElementById('newRequestForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const caseId = formData.get('case_id');

    // Parse mobile_numbers from textarea (comma or newline separated)
    const rawNumbers = formData.get('mobile_number');
    const mobileNumbers = rawNumbers.split(/[\n,]+/).map(n => n.trim()).filter(n => n.length > 0);

    if (mobileNumbers.length === 0) {
        showAlert('danger', 'Please enter at least one mobile number.');
        return;
    }

    const payload = {
        mobile_numbers: mobileNumbers,
        request_type: formData.get('request_type'),
        reason: formData.get('reason')
    };

    try {
        // Use Batch Endpoint
        const response = await API.createBatchRequests(null, caseId, payload);

        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('newRequestModal'));
        modal.hide();

        // Reset form
        document.getElementById('newRequestForm').reset();

        // Refresh list
        loadRequests();

        // Show success
        showAlert('success', `Successfully generated ${response.length} grouped request(s) for ${mobileNumbers.length} numbers.`);
    } catch (err) {
        showAlert('danger', err.message);
    }
});

// Review Handling
let currentReviewId = null;
function openReview(id) {
    currentReviewId = id;
    const modal = new bootstrap.Modal(document.getElementById('reviewModal'));
    document.getElementById('reviewRequestId').innerText = id;
    modal.show();
}

async function submitReview(action, providedReason = null) {
    if (!currentReviewId) return;

    try {
        if (action === 'approve') {
            await API.approveRequest(null, currentReviewId);
        } else {
            const reason = providedReason || prompt("Enter rejection reason:");
            if (!reason) return;
            await API.rejectRequest(null, currentReviewId, reason);
        }

        const modal = bootstrap.Modal.getInstance(document.getElementById('reviewModal'));
        modal.hide();
        showAlert('success', `Request ${action}d successfully`);
        loadRequests();
    } catch (err) {
        showAlert('danger', `Failed to ${action} request`);
    }
}

// Email Draft Logic
let currentEmailReqId = null;

function generateEmailDraft(reqId) {
    const req = allRequests.find(r => r.id === reqId);
    if (!req) return;

    currentEmailReqId = reqId;
    const modal = new bootstrap.Modal(document.getElementById('emailDraftModal'));
    const mobile = req.mobile_number;
    const type = req.request_type;
    const caseId = req.case_id;

    // Detect TSP
    let tspEmail = "";
    if (req.reason.includes("Airtel")) tspEmail = "nodal.officer@airtel.com";
    else if (req.reason.includes("Jio")) tspEmail = "disclosure.officer@jio.com";
    else if (req.reason.includes("Vodafone")) tspEmail = "nodal@vodafoneidea.com";
    else if (req.reason.includes("BSNL")) tspEmail = "learequest@bsnl.co.in";

    const emailSelect = document.getElementById('emailTo');
    if (tspEmail) emailSelect.value = tspEmail;
    else emailSelect.selectedIndex = 0;

    // Set Default Template
    document.getElementById('emailTemplate').value = "standard";
    applyTemplate(); // Generates body/subject

    // PDF Preview via authenticated Blob URL (never expose JWT in URL query)
    document.getElementById('previewFilename').innerText = `REQ_${reqId}.pdf`;
    document.getElementById('pdfLoading').classList.remove('d-none');

    const previewFrame = document.getElementById('pdfPreviewFrame');
    let previewBlobUrl = null;
    apiFetch(`/requests/${reqId}/download`)
        .then(resp => {
            if (!resp.ok) throw new Error('Failed to load requisition PDF');
            return resp.blob();
        })
        .then(blob => {
            previewBlobUrl = URL.createObjectURL(blob);
            previewFrame.src = previewBlobUrl;
        })
        .catch(() => {
            document.getElementById('pdfLoading').classList.add('d-none');
        });

    previewFrame.onload = () => {
        document.getElementById('pdfLoading').classList.add('d-none');
    };
    document.getElementById('emailDraftModal').addEventListener('hidden.bs.modal', () => {
        if (previewBlobUrl) {
            URL.revokeObjectURL(previewBlobUrl);
            previewBlobUrl = null;
            previewFrame.src = '';
        }
    }, { once: true });

    // Download Button
    document.getElementById('downloadReqBtn').onclick = () => API.downloadRequestLetter(null, reqId);

    // Reset "Mark Sent" Button
    const sentBtn = document.getElementById('markSentBtn');
    sentBtn.classList.add('disabled');
    sentBtn.classList.remove('btn-success');
    sentBtn.classList.add('btn-secondary');
    sentBtn.innerText = "MARK AS SENT";

    modal.show();
}

function applyTemplate() {
    if (!currentEmailReqId) return;
    const req = allRequests.find(r => r.id === currentEmailReqId);
    if (!req) return;

    const template = document.getElementById('emailTemplate').value;
    const subjectEl = document.getElementById('emailSubject');
    const bodyEl = document.getElementById('emailBody');
    const emailSelect = document.getElementById('emailTo');
    const recipient = emailSelect.options[emailSelect.selectedIndex].text.split('(')[0].trim();

    let subject = "";
    let prefix = "";

    if (template === 'urgent') {
        subject = `URGENT: LIFE THREATENING EMERGENCY | Disclosure Request | ${req.mobile_number}`;
        prefix = "URGENT / EMERGENCY DISCLOSURE";
    } else if (template === 'reminder') {
        subject = `REMINDER-1: Pending Disclosure for Case ${req.case_id} | ${req.mobile_number}`;
        prefix = "REMINDER / IMMEDIATE ACTION";
    } else {
        subject = `Lawful Disclosure Request | ${req.request_type} | Case ${req.case_id}`;
        prefix = "OFFICIAL REQUISITION";
    }

    subjectEl.value = subject;

    bodyEl.value = `To,
The Nodal Officer,
${recipient}

Subject: ${subject}

Ref: Investigation in Case FIR No. ${req.case_id}

Respected Sir/Madam,

[${prefix}]

In exercise of the powers conferred under Section 94 of the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023, you are hereby requested to provide the ${req.request_type} details for:

Mobile Number(s):
${req.mobile_number}

The requested information is essentially required for a sensitive criminal investigation. 
Please find the officially signed Requisition Letter attached.

Regards,
Inspector In-Charge,
Cyber Crime Investigation Cell.`;

    updateMailto();
}

// Enable "Mark as Sent" only after clicking "Open Mail App"
function enableMarkSent() {
    const sentBtn = document.getElementById('markSentBtn');
    sentBtn.classList.remove('disabled', 'btn-secondary');
    sentBtn.classList.add('btn-success');
}

async function markRequestAsSent() {
    if (!currentEmailReqId) return;

    try {
        await API.dispatchRequest(null, currentEmailReqId);

        const modal = bootstrap.Modal.getInstance(document.getElementById('emailDraftModal'));
        modal.hide();

        showAlert('success', 'Request marked as DISPATCHED successfully.');
        loadRequests();

    } catch (err) {
        showAlert('danger', 'Failed to update status: ' + err.message);
    }
}

function updateMailto() {
    const to = document.getElementById('emailTo').value;
    const subject = encodeURIComponent(document.getElementById('emailSubject').value);
    const body = encodeURIComponent(document.getElementById('emailBody').value);
    document.getElementById('mailtoLink').href = `mailto:${to}?subject=${subject}&body=${body}`;
}

// Event Listeners for Dynamic Updates
document.getElementById('emailTo')?.addEventListener('change', () => {
    applyTemplate(); // Re-generate body with new recipient name
});

function copyEmailToClipboard() {
    const subject = document.getElementById('emailSubject').value;
    const body = document.getElementById('emailBody').value;
    const text = `Subject: ${subject}\n\n${body}`;

    navigator.clipboard.writeText(text).then(() => {
        showAlert('success', "Draft copied to clipboard!");
    });
}

function showAlert(type, msg) {
    const ph = document.getElementById('alertPlaceholder');
    ph.innerHTML = `
        <div class="alert alert-${escapeHtml(type)} alert-dismissible fade show" role="alert">
            <span class="alert-msg"></span>
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    ph.querySelector('.alert-msg').textContent = msg;
    setTimeout(() => {
        ph.innerHTML = '';
    }, 5000);
}

// Manual Upload Handling
let uploadTargetRequestId = null;

function uploadSignedCopy(reqId) {
    uploadTargetRequestId = reqId;
    document.getElementById('signedUploadInput')?.click();
}

document.getElementById('signedUploadInput')?.addEventListener('change', async (e) => {
    if (!uploadTargetRequestId || !e.target.files[0]) return;

    const file = e.target.files[0];
    const formData = new FormData();
    formData.append('file', file);

    try {
        await API.uploadRequestFile(null, uploadTargetRequestId, formData);
        showAlert('success', 'Signed Copy Uploaded Successfully');
        loadRequests(); // Refresh to ensure backend path updates
    } catch (err) {
        showAlert('danger', 'Upload Failed: ' + err.message);
    } finally {
        e.target.value = ''; // Reset input
        uploadTargetRequestId = null;
    }
});

// Expose filter helpers globally for inline HTML event handlers
window.filterRequests = filterRequests;
window.clearRequestFilters = clearRequestFilters;

init();
