// Global variables for filtering
let allCases = [];

// Filter and search cases
function filterCases() {
    const searchTerm = (document.getElementById('caseSearchInput')?.value || '').toLowerCase();
    const statusFilter = (document.getElementById('statusFilter')?.value || '').toLowerCase();
    const sortBy = document.getElementById('sortBy')?.value || 'date_desc';

    // Filter cases
    let filtered = allCases.filter(c => {
        const matchesSearch =
            c.fir_number.toLowerCase().includes(searchTerm) ||
            c.police_station.toLowerCase().includes(searchTerm) ||
            (c.case_type && c.case_type.toLowerCase().includes(searchTerm)) ||
            (c.description && c.description.toLowerCase().includes(searchTerm));

        const matchesStatus = !statusFilter || c.status.toLowerCase() === statusFilter;

        return matchesSearch && matchesStatus;
    });

    // Sort cases
    filtered.sort((a, b) => {
        switch (sortBy) {
            case 'date_asc':
                return new Date(a.created_at) - new Date(b.created_at);
            case 'date_desc':
                return new Date(b.created_at) - new Date(a.created_at);
            case 'fir_asc':
                return a.fir_number.localeCompare(b.fir_number);
            case 'fir_desc':
                return b.fir_number.localeCompare(a.fir_number);
            default:
                return new Date(b.created_at) - new Date(a.created_at);
        }
    });

    // Update result count
    const resultCount = document.getElementById('resultCount');
    if (resultCount) resultCount.textContent = filtered.length;

    const totalCount = document.getElementById('totalCount');
    if (totalCount) totalCount.textContent = allCases.length;

    // Render filtered results
    if (typeof renderTable === 'function') {
        renderTable(filtered);
    }
}

// Clear all filters
function clearFilters() {
    const searchInput = document.getElementById('caseSearchInput');
    if (searchInput) searchInput.value = '';

    const statusFilter = document.getElementById('statusFilter');
    if (statusFilter) statusFilter.value = '';

    const sortBy = document.getElementById('sortBy');
    if (sortBy) sortBy.value = 'date_desc';

    filterCases();
}

// Expose to global scope
window.filterCases = filterCases;
window.clearFilters = clearFilters;
window.allCases = allCases;
