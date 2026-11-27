// Dynamic API URL based on environment
const API_URL = (() => {
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        return `${window.location.protocol}//${window.location.hostname}:8001`;
    }
    return window.location.origin;
})();

function getCookie(name) {
    const match = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : '';
}

async function apiFetch(pathOrUrl, options = {}) {
    const url = pathOrUrl.startsWith('http') ? pathOrUrl : `${API_URL}${pathOrUrl}`;
    const method = (options.method || 'GET').toUpperCase();
    const headers = new Headers(options.headers || {});
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
        const csrf = getCookie('csrf_token');
        if (csrf) headers.set('X-CSRF-Token', csrf);
    }
    return fetch(url, {
        ...options,
        method,
        headers,
        credentials: 'include',
    });
}

window.API_URL = API_URL;
window.apiFetch = apiFetch;

class API {
    static async login(username, password) {
        const formData = new FormData();
        formData.append("username", username);
        formData.append("password", password);

        const response = await apiFetch(`/auth/token`, {
            method: "POST",
            body: formData,
        });
        if (!response.ok) throw new Error("Login failed");
        return response.json();
    }

    static async register(username, email, password, role = "officer", _token = null, jurisdiction = {}) {
        const payload = { username, email, password, role };
        if (jurisdiction.station_name) payload.station_name = jurisdiction.station_name;
        if (jurisdiction.sub_division) payload.sub_division = jurisdiction.sub_division;
        if (jurisdiction.district_name) payload.district_name = jurisdiction.district_name;
        if (jurisdiction.range_name) payload.range_name = jurisdiction.range_name;
        if (jurisdiction.zone_name) payload.zone_name = jurisdiction.zone_name;

        const response = await apiFetch(`/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Registration failed");
        }
        return response.json();
    }

    static async getMe() {
        const response = await apiFetch(`/auth/me`);
        if (!response.ok) throw new Error("Failed to fetch user");
        return response.json();
    }

    static async getCases() {
        const response = await apiFetch(`/cases/`);
        if (!response.ok) throw new Error("Failed to fetch cases");
        return response.json();
    }

    static async createCase(_token, caseData) {
        const payload = caseData || _token;
        const response = await apiFetch(`/cases/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to create case");
        }
        return response.json();
    }

    static async getRequests() {
        const response = await apiFetch(`/requests/`);
        if (!response.ok) throw new Error("Failed to fetch requests");
        return response.json();
    }

    static async createRequest(_token, caseId, requestData) {
        const response = await apiFetch(`/requests/?case_id=${caseId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(requestData),
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to create request");
        }
        return response.json();
    }

    static async createBatchRequests(_token, caseId, batchData) {
        const response = await apiFetch(`/requests/batch?case_id=${caseId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(batchData),
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to create batch requests");
        }
        return response.json();
    }

    static async approveRequest(_token, requestId) {
        const response = await apiFetch(`/requests/${requestId}/approve`, { method: "POST" });
        if (!response.ok) throw new Error("Failed to approve request");
        return response.json();
    }

    static async rejectRequest(_token, requestId, reason) {
        const response = await apiFetch(`/requests/${requestId}/reject?reason=${encodeURIComponent(reason)}`, { method: "POST" });
        if (!response.ok) throw new Error("Failed to reject request");
        return response.json();
    }

    static async dispatchRequest(_token, requestId) {
        const response = await apiFetch(`/requests/${requestId}/dispatch`, { method: "POST" });
        if (!response.ok) throw new Error("Failed to dispatch request");
        return response.json();
    }

    static async getCase(_token, id) {
        const caseId = id !== undefined ? id : _token;
        const response = await apiFetch(`/cases/${caseId}`);
        if (!response.ok) throw new Error("Failed to fetch case");
        return response.json();
    }

    static async updateCaseStatus(_token, id, status) {
        const response = await apiFetch(`/cases/${id}/status`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status }),
        });
        if (!response.ok) throw new Error("Failed to update status");
        return response.json();
    }

    static async getEvidence(_token, caseId) {
        const cid = caseId !== undefined ? caseId : _token;
        const response = await apiFetch(`/files/case/${cid}`);
        if (!response.ok) throw new Error("Failed to fetch evidence");
        return response.json();
    }

    static async uploadEvidence(_token, caseId, formData) {
        const response = await apiFetch(`/files/upload/${caseId}`, {
            method: "POST",
            body: formData,
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || "Upload failed");
        }
        return response.json();
    }

    static async downloadEvidence(_token, id) {
        const evId = id !== undefined ? id : _token;
        const response = await apiFetch(`/files/download/${evId}`);
        if (!response.ok) throw new Error("Download failed");

        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'evidence_file';
        if (contentDisposition) {
            const matches = /filename="?([^"]+)"?/.exec(contentDisposition);
            if (matches && matches[1]) filename = matches[1];
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    }

    static async downloadRequestLetter(_token, requestId) {
        const rid = requestId !== undefined ? requestId : _token;
        const response = await apiFetch(`/requests/${rid}/download`);
        if (!response.ok) throw new Error("Failed to download requisition letter");

        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `REQ_${rid}.pdf`;
        if (contentDisposition) {
            const matches = /filename="?([^"]+)"?/.exec(contentDisposition);
            if (matches && matches[1]) filename = matches[1];
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    }

    static async uploadRequestFile(_token, requestId, formData) {
        const response = await apiFetch(`/requests/${requestId}/upload`, {
            method: "POST",
            body: formData,
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || "Upload failed");
        }
        return response.json();
    }

    static async analyzeCDR(_token, evidenceId) {
        const eid = evidenceId !== undefined ? evidenceId : _token;
        const response = await apiFetch(`/analysis/cdr/${eid}`);
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Analysis failed");
        }
        return response.json();
    }

    static async getAuditLogs() {
        const response = await apiFetch(`/admin/logs`);
        if (!response.ok) throw new Error("Failed to fetch logs");
        return response.json();
    }

    static async searchCrossCase(_token, mobileNumber) {
        const mob = mobileNumber !== undefined ? mobileNumber : _token;
        const response = await apiFetch(`/analysis/correlate/${mob}`);
        if (!response.ok) throw new Error("Search failed");
        return response.json();
    }

    static async changePassword(_token, oldPassword, newPassword) {
        const response = await apiFetch(`/auth/change-password`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                old_password: oldPassword,
                new_password: newPassword,
            }),
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Password update failed");
        }
        return response.json();
    }

    static async createFinancialEntity(_token, caseId, entityData) {
        const response = await apiFetch(`/financial-entities/${caseId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(entityData),
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to add financial entity");
        }
        return response.json();
    }

    static async getFinancialEntities(_token, caseId) {
        const cid = caseId !== undefined ? caseId : _token;
        const response = await apiFetch(`/financial-entities/${cid}`);
        if (!response.ok) throw new Error("Failed to fetch financial entities");
        return response.json();
    }

    static async createNPCIRequest(_token, caseId, requestData) {
        const response = await apiFetch(`/npci/requests/${caseId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(requestData),
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to create NPCI request");
        }
        return response.json();
    }

    static async logout() {
        try {
            await apiFetch(`/auth/logout`, { method: "POST" });
        } catch (_err) {
            // Proceed even if offline
        }
    }

    static async getBsa63Manifest(_token, caseId) {
        const cid = caseId !== undefined ? caseId : _token;
        const response = await apiFetch(`/files/case/${cid}/bsa63-manifest`);
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || "Failed to fetch Section 63 BSA manifest");
        }
        return response.json();
    }

    static async createFreezeRequest(_token, caseId, payload) {
        const response = await apiFetch(`/freeze/request/${caseId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || "Failed to initiate freeze request");
        }
        return response.json();
    }

    static async getFreezeRequests() {
        const response = await apiFetch(`/freeze/requests/`);
        if (!response.ok) throw new Error("Failed to fetch freeze requests");
        return response.json();
    }

    static async updateFreezeStatus(requestId, status, bankReference = null) {
        let url = `/freeze/requests/${requestId}/status?status=${encodeURIComponent(status)}`;
        if (bankReference) url += `&bank_reference=${encodeURIComponent(bankReference)}`;
        const response = await apiFetch(url, { method: "PATCH" });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || "Failed to update freeze request status");
        }
        return response.json();
    }

    static async verifyAuditChain() {
        const response = await apiFetch(`/admin/logs/verify`);
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || "Audit chain verification failed");
        }
        return response.json();
    }

    static async getCaseTimeline(_token, caseId) {
        const cid = caseId !== undefined ? caseId : _token;
        const response = await apiFetch(`/analytics/timeline/${cid}`);
        if (!response.ok) throw new Error("Failed to fetch case timeline");
        return response.json();
    }

    static async getCaseRequests(_token, caseId) {
        const cid = caseId !== undefined ? caseId : _token;
        const response = await apiFetch(`/requests/?case_id=${encodeURIComponent(cid)}`);
        if (!response.ok) throw new Error("Failed to fetch case requests");
        return response.json();
    }

    static async analyzeTowerCoLocation(caseId, windowMinutes = 15) {
        const response = await apiFetch(
            `/analysis/tower-co-location?case_id=${encodeURIComponent(caseId)}&window_minutes=${encodeURIComponent(windowMinutes)}`,
            { method: "POST" }
        );
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || "Tower co-location analysis failed");
        }
        return response.json();
    }
}
