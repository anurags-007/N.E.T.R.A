// Global variables for filtering requests
let allRequests = [];

// Filter and search requests
function filterRequests() {
    const searchTerm = (document.getElementById('requestSearchInput')?.value || '').toLowerCase();
    const statusFilter = (document.getElementById('requestStatusFilter')?.value || '').toLowerCase();
    const typeFilter = (document.getElementById('requestTypeFilter')?.value || '');
    const sortBy = document.getElementById('requestSortBy')?.value || 'date_desc';

    // Filter requests
    let filtered = allRequests.filter(r => {
        const matchesSearch =
            String(r.id).includes(searchTerm) ||
            (r.mobile_number && r.mobile_number.includes(searchTerm)) ||
            (r.case && r.case.fir_number && r.case.fir_number.toLowerCase().includes(searchTerm)) ||
            (r.reason && r.reason.toLowerCase().includes(searchTerm));

        const matchesStatus = !statusFilter || r.status.toLowerCase() === statusFilter;
        const matchesType = !typeFilter || r.request_type === typeFilter;

        return matchesSearch && matchesStatus && matchesType;
    });

    // Sort requests
    filtered.sort((a, b) => {
        switch (sortBy) {
            case 'date_asc':
                return new Date(a.created_at) - new Date(b.created_at);
            case 'date_desc':
                return new Date(b.created_at) - new Date(a.created_at);
            case 'id_asc':
                return a.id - b.id;
            case 'id_desc':
                return b.id - a.id;
            default:
                return new Date(b.created_at) - new Date(a.created_at);
        }
    });

    // Update result count
    const resultCount = document.getElementById('requestResultCount');
    if (resultCount) resultCount.textContent = filtered.length;

    const totalCount = document.getElementById('requestTotalCount');
    if (totalCount) totalCount.textContent = allRequests.length;

    // Render filtered results
    if (typeof renderRequestsTable === 'function') {
        renderRequestsTable(filtered);
    }
}

// Clear all filters
function clearRequestFilters() {
    const searchInput = document.getElementById('requestSearchInput');
    if (searchInput) searchInput.value = '';

    const statusFilter = document.getElementById('requestStatusFilter');
    if (statusFilter) statusFilter.value = '';

    const typeFilter = document.getElementById('requestTypeFilter');
    if (typeFilter) typeFilter.value = '';

    const sortBy = document.getElementById('requestSortBy');
    if (sortBy) sortBy.value = 'date_desc';

    filterRequests();
}

// Expose to global scope
window.filterRequests = filterRequests;
window.clearRequestFilters = clearRequestFilters;
window.allRequests = allRequests;
