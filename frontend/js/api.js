// Dynamic API URL based on environment
const API_URL = (() => {
    // If running on localhost, use port 8001
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        return `${window.location.protocol}//${window.location.hostname}:8001`;
    }
    // In production, assume API is on same domain
    return window.location.origin;
})();


class API {
    static async login(username, password) {
        const formData = new FormData();
        formData.append("username", username);
        formData.append("password", password);

        const response = await fetch(`${API_URL}/auth/token`, {
            method: "POST",
            body: formData,
        });
        if (!response.ok) throw new Error("Login failed");
        return response.json();
    }

    static async register(username, email, password, role = "officer", token) {
        const response = await fetch(`${API_URL}/auth/register`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ username, email, password, role }),
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Registration failed");
        }
        return response.json();
    }

    static async getMe(token) {
        const response = await fetch(`${API_URL}/auth/me`, {
            headers: { "Authorization": `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Failed to fetch user");
        return response.json();
    }

    static async getCases(token) {
        const response = await fetch(`${API_URL}/cases/`, {
            headers: { "Authorization": `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Failed to fetch cases");
        return response.json();
    }

    static async createCase(token, caseData) {
        const response = await fetch(`${API_URL}/cases/`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json",
            },
            body: JSON.stringify(caseData),
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to create case");
        }
        return response.json();
    }

    static async getRequests(token) {
        const response = await fetch(`${API_URL}/requests/`, {
            headers: { "Authorization": `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Failed to fetch requests");
        return response.json();
    }

    static async createRequest(token, caseId, requestData) {
        const response = await fetch(`${API_URL}/requests/?case_id=${caseId}`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json",
            },
            body: JSON.stringify(requestData),
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to create request");
        }
        return response.json();
    }

    static async approveRequest(token, requestId) {
        const response = await fetch(`${API_URL}/requests/${requestId}/approve`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Failed to approve request");
        return response.json();
    }

    static async rejectRequest(token, requestId, reason) {
        const response = await fetch(`${API_URL}/requests/${requestId}/reject?reason=${encodeURIComponent(reason)}`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Failed to reject request");
        return response.json();
    }

    static async dispatchRequest(token, requestId) {
        const response = await fetch(`${API_URL}/requests/${requestId}/dispatch`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Failed to dispatch request");
        return response.json();
    }

    static async getCase(token, id) {
        const response = await fetch(`${API_URL}/cases/${id}`, {
            headers: { "Authorization": `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Failed to fetch case");
        return response.json();
    }

    static async updateCaseStatus(token, id, status) {
        const response = await fetch(`${API_URL}/cases/${id}/status`, {
            method: "PATCH",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ status })
        });
        if (!response.ok) throw new Error("Failed to update status");
        return response.json();
    }

    static async getEvidence(token, caseId) {
        const response = await fetch(`${API_URL}/files/case/${caseId}`, {
            headers: { "Authorization": `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Failed to fetch evidence");
        return response.json();
    }

    static async uploadEvidence(token, caseId, formData) {
        const response = await fetch(`${API_URL}/files/upload/${caseId}`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` }, // No Content-Type for FormData
            body: formData,
        });
        if (!response.ok) throw new Error("Upload failed");
        return response.json();
    }

    static async downloadEvidence(token, id) {
        // FIX: Use POST request to avoid exposing token in URL
        const response = await fetch(`${API_URL}/files/download/${id}`, {
            method: "GET",
            headers: { "Authorization": `Bearer ${token}` },
        });

        if (!response.ok) throw new Error("Download failed");

        // Get filename from Content-Disposition header
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'evidence_file';
        if (contentDisposition) {
            const matches = /filename="?([^"]+)"?/.exec(contentDisposition);
            if (matches && matches[1]) {
                filename = matches[1];
            }
        }

        // Download file
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

    static async downloadRequestLetter(token, requestId) {
        window.location.href = `${API_URL}/requests/${requestId}/download?token=${token}`;
    }

    static async uploadRequestFile(token, requestId, formData) {
        const response = await fetch(`${API_URL}/requests/${requestId}/upload`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` },
            body: formData,
        });
        if (!response.ok) throw new Error("Upload failed");
        return response.json();
    }

    static async analyzeCDR(token, evidenceId) {
        const response = await fetch(`${API_URL}/analysis/cdr/${evidenceId}`, {
            headers: { "Authorization": `Bearer ${token}` },
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Analysis failed");
        }
        return response.json();
    }

    static async getAuditLogs(token) {
        const response = await fetch(`${API_URL}/admin/logs`, {
            headers: { "Authorization": `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Failed to fetch logs");
        return response.json();
    }

    static async searchCrossCase(token, mobileNumber) {
        const response = await fetch(`${API_URL}/analysis/correlate/${mobileNumber}`, {
            headers: { "Authorization": `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Search failed");
        return response.json();
    }

    static async changePassword(token, oldPassword, newPassword) {
        const response = await fetch(`${API_URL}/auth/change-password`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                old_password: oldPassword,
                new_password: newPassword
            })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Password update failed");
        }
        return response.json();
    }

    // ========== FINANCIAL MODULE API ==========

    static async createFinancialEntity(token, caseId, entityData) {
        const response = await fetch(`${API_URL}/financial-entities/${caseId}`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify(entityData)
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to add financial entity");
        }
        return response.json();
    }

    static async getFinancialEntities(token, caseId) {
        const response = await fetch(`${API_URL}/financial-entities/${caseId}`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (!response.ok) throw new Error("Failed to fetch financial entities");
        return response.json();
    }

    static async createNPCIRequest(token, caseId, requestData) {
        const response = await fetch(`${API_URL}/npci/requests/${caseId}`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify(requestData)
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Failed to create NPCI request");
        }
        return response.json();
    }
}
