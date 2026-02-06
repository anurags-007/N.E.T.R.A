const token = localStorage.getItem('token');
let currentUser = null;
let allRequests = []; // Cache for requests
let allCases = []; // Cache for cases

if (!token) {
    window.location.href = 'index.html';
}

// Logout
document.getElementById('logoutBtn').addEventListener('click', () => {
    localStorage.removeItem('token');
    window.location.href = 'index.html';
});

async function init() {
    try {
        currentUser = await API.getMe(token);

        // Fix Profile Display
        document.getElementById('userNameDisplay').textContent = currentUser.username;
        const roleDisplay = document.getElementById('userRoleDisplay');
        if (roleDisplay) {
            const payload = JSON.parse(atob(token.split('.')[1]));
            roleDisplay.textContent = (payload.rank || currentUser.role).toUpperCase();
        }

        loadRequests();
        loadCasesForSelect();

    } catch (err) {
        console.error(err);
        localStorage.removeItem('token');
        window.location.href = 'index.html';
    }
}

async function loadRequests() {
    try {
        allRequests = await API.getRequests(token); // Store in cache
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

        let actionButtons = '';
        // FIX: role value is 'sho' for Inspector (SHO)
        // Check permissions
        const isAuthorized = ['sho', 'admin', 'dy_sp', 'sp', 'dig', 'igp', 'dgp'].includes(currentUser.role);

        if (isAuthorized && r.status === 'pending') {
            actionButtons = `
                <button class="btn btn-sm btn-success" onclick="openReview(${r.id})">Review</button>
            `;
        } else if (r.status === 'approved') {
            actionButtons = `
                <button class="btn btn-sm btn-outline-secondary me-1" onclick="uploadSignedCopy(${r.id})">
                    <i class="bi bi-upload"></i> Upload Signed
                </button>
                <button class="btn btn-sm btn-outline-dark" onclick="generateEmailDraft(${r.id})">
                    <i class="bi bi-envelope-at"></i> Email Draft
                </button>
            `;
        } else if (r.status === 'dispatched') {
            actionButtons = `
                <button class="btn btn-sm btn-success disabled">
                    <i class="bi bi-check2-all"></i> Sent
                </button>
            `;
        }

        // Calculate Pending Days
        const createdDate = new Date(r.created_at);
        const now = new Date();
        const diffTime = Math.abs(now - createdDate);
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

        let statusBadge = `<span class="badge bg-${getStatusColor(r.status)}">${r.status.toUpperCase()}</span>`;

        // Highlight aging requests
        if (r.status === 'pending' && diffDays > 7) {
            statusBadge += ` <span class="badge bg-danger ms-1" title="Escalation Required"><i class="bi bi-clock-history"></i> ${diffDays}d</span>`;
        }

        // Lookup Case Info
        const linkedCase = allCases.find(c => c.id === r.case_id);
        const caseDisplay = linkedCase ? `${linkedCase.fir_number}` : `Case #${r.case_id}`;

        tr.innerHTML = `
            <td>#${r.id}</td>
            <td><span class="badge bg-light text-dark border">${caseDisplay}</span></td>
            <td class="font-monospace">${r.mobile_number}</td>
            <td>${r.request_type}</td>
            <td>${statusBadge}</td>
            <td><small class="text-muted text-truncate d-inline-block" style="max-width: 150px;">${r.rejection_reason || r.reason}</small></td>
            <td>${actionButtons}</td>
        `;
        tbody.appendChild(tr);
    });
}

async function loadCasesForSelect() {
    try {
        allCases = await API.getCases(token); // Cache cases
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
    'BNSS_94': 'In exercise of the powers conferred under Section 94 of the Bharatiya Nagarik Suraksha Sanhita (BNSS), the requested data is required for the purpose of ongoing investigation in the linked case to establish identity and trace suspects.',
    'CRPC_91': 'Data requisitioned under Section 91 of the Code of Criminal Procedure (CrPC) for the production of documents or other things necessary for the purpose of the investigation in the mentioned FIR.',
    'CRPC_102': 'Seeking information under Section 102 of CrPC regarding property (telecommunications data) which may be found under circumstances which create suspicion of the commission of any offence.',
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
        const response = await API.createBatchRequests(token, caseId, payload);

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

async function submitReview(action) {
    if (!currentReviewId) return;

    try {
        if (action === 'approve') {
            await API.approveRequest(token, currentReviewId);
        } else {
            const reason = prompt("Enter rejection reason:"); // Simple prompt for now, or use the modal input
            if (!reason) return;
            await API.rejectRequest(token, currentReviewId, reason);
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

    // PDF Preview
    document.getElementById('previewFilename').innerText = `REQ_${reqId}.pdf`;
    document.getElementById('pdfLoading').classList.remove('d-none');

    // Use the download endpoint for preview (browser handles PDF)
    const pdfUrl = `${API_URL}/requests/${reqId}/download?token=${token}`;
    document.getElementById('pdfPreviewFrame').src = pdfUrl;
    document.getElementById('pdfPreviewFrame').onload = () => {
        document.getElementById('pdfLoading').classList.add('d-none');
    };

    // Download Button
    document.getElementById('downloadReqBtn').onclick = () => API.downloadRequestLetter(token, reqId);

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

In exercise of the powers conferred under Section 91 of the Code of Criminal Procedure (CrPC), you are hereby requested to provide the ${req.request_type} details for:

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
        await API.dispatchRequest(token, currentEmailReqId);

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
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${msg}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    setTimeout(() => {
        ph.innerHTML = '';
    }, 5000);
}

// Manual Upload Handling
let uploadTargetRequestId = null;

function uploadSignedCopy(reqId) {
    uploadTargetRequestId = reqId;
    document.getElementById('signedUploadInput').click();
}

document.getElementById('signedUploadInput').addEventListener('change', async (e) => {
    if (!uploadTargetRequestId || !e.target.files[0]) return;

    const file = e.target.files[0];
    const formData = new FormData();
    formData.append('file', file);

    try {
        await API.uploadRequestFile(token, uploadTargetRequestId, formData);
        showAlert('success', 'Signed Copy Uploaded Successfully');
        loadRequests(); // Refresh to ensure backend path updates
    } catch (err) {
        showAlert('danger', 'Upload Failed: ' + err.message);
    } finally {
        e.target.value = ''; // Reset input
        uploadTargetRequestId = null;
    }
});

init();
