const SUPABASE_URL = "https://cpavwkdonvkvrwygfzfo.supabase.co";
const ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNwYXZ3a2RvbnZrdnJ3eWdmemZvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIzNjAyODMsImV4cCI6MjA5NzkzNjI4M30.-_FAsA2csTrB9qt267pBfjJkczMP7pcaUi4plMv3kv4";
const PAGE_SIZE = 24;

// App State
let state = {
    searchTerm: '',
    status: 'active',
    isChild: false,
    currentPage: 0,
    totalCount: 0
};

// DOM Elements
const searchInput = document.getElementById('search-input');
const clearSearchBtn = document.getElementById('clear-search');
const statusFilter = document.getElementById('status-filter');
const childFilter = document.getElementById('child-filter');
const exportCsvBtn = document.getElementById('export-csv-btn');
const resultsCount = document.getElementById('results-count');
const resultsGrid = document.getElementById('results-grid');
const loader = document.getElementById('loader');
const emptyState = document.getElementById('empty-state');
const paginationContainer = document.getElementById('pagination');
const prevPageBtn = document.getElementById('prev-page');
const nextPageBtn = document.getElementById('next-page');
const pageIndicator = document.getElementById('page-indicator');
const statMissingVal = document.querySelector('#stat-missing .stat-value');
const statFoundVal = document.querySelector('#stat-found .stat-value');

// Debounce timer for search
let debounceTimer;

// Init
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    fetchStats();
    loadData();
});

function setupEventListeners() {
    // Search input
    searchInput.addEventListener('input', (e) => {
        state.searchTerm = e.target.value;
        if (state.searchTerm.length > 0) {
            clearSearchBtn.style.display = 'block';
        } else {
            clearSearchBtn.style.display = 'none';
        }
        
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            state.currentPage = 0;
            loadData();
        }, 300);
    });

    // Clear search
    clearSearchBtn.addEventListener('click', () => {
        searchInput.value = '';
        state.searchTerm = '';
        clearSearchBtn.style.display = 'none';
        state.currentPage = 0;
        loadData();
    });

    // Status filter
    statusFilter.addEventListener('change', (e) => {
        state.status = e.target.value;
        state.currentPage = 0;
        loadData();
    });

    // Child filter
    childFilter.addEventListener('change', (e) => {
        state.isChild = e.target.checked;
        state.currentPage = 0;
        loadData();
    });

    // Pagination
    prevPageBtn.addEventListener('click', () => {
        if (state.currentPage > 0) {
            state.currentPage--;
            loadData();
            scrollToResults();
        }
    });

    nextPageBtn.addEventListener('click', () => {
        const maxPages = Math.ceil(state.totalCount / PAGE_SIZE);
        if (state.currentPage < maxPages - 1) {
            state.currentPage++;
            loadData();
            scrollToResults();
        }
    });

    // Export CSV
    exportCsvBtn.addEventListener('click', exportCSV);
}

function scrollToResults() {
    document.querySelector('.results-section').scrollIntoView({ behavior: 'smooth' });
}

// Fetch general stats (totals)
async function fetchStats() {
    const headers = {
        'apikey': ANON_KEY,
        'Authorization': `Bearer ${ANON_KEY}`,
        'Prefer': 'count=exact'
    };

    try {
        const [missingRes, foundRes] = await Promise.all([
            fetch(`${SUPABASE_URL}/rest/v1/missing_persons?status=eq.active&select=id`, { 
                method: 'HEAD', 
                headers: { ...headers, 'Range': '0-0' }
            }),
            fetch(`${SUPABASE_URL}/rest/v1/missing_persons?status=eq.found&select=id`, { 
                method: 'HEAD', 
                headers: { ...headers, 'Range': '0-0' }
            })
        ]);

        const missingRange = missingRes.headers.get('Content-Range');
        const foundRange = foundRes.headers.get('Content-Range');

        if (missingRange && missingRange.includes('/')) {
            statMissingVal.textContent = parseInt(missingRange.split('/')[1]).toLocaleString();
        }
        if (foundRange && foundRange.includes('/')) {
            statFoundVal.textContent = parseInt(foundRange.split('/')[1]).toLocaleString();
        }
    } catch (error) {
        console.error('Error fetching global stats:', error);
    }
}

// Build query URL based on filters
function buildQueryUrl(isExport = false) {
    let url = `${SUPABASE_URL}/rest/v1/missing_persons?select=*&status=eq.${state.status}`;
    
    if (state.isChild) {
        url += '&is_child=eq.true';
    }

    if (state.searchTerm.trim() !== '') {
        const cleanTerm = state.searchTerm.replace(/[%,()]/g, ' ').trim();
        if (cleanTerm !== '') {
            // Search in name, description, or last_seen
            url += `&or=(name.ilike.*${encodeURIComponent(cleanTerm)}*,description.ilike.*${encodeURIComponent(cleanTerm)}*,last_seen.ilike.*${encodeURIComponent(cleanTerm)}*)`;
        }
    }

    // Default order
    url += '&order=ext_created.desc';

    if (isExport) {
        url += '&limit=5000'; // Limit exports to prevent browser freeze
    }

    return url;
}

// Main load data function
async function loadData() {
    showLoader(true);
    resultsGrid.innerHTML = '';
    emptyState.style.display = 'none';
    paginationContainer.style.display = 'none';

    const url = buildQueryUrl();
    const offset = state.currentPage * PAGE_SIZE;

    const headers = {
        'apikey': ANON_KEY,
        'Authorization': `Bearer ${ANON_KEY}`,
        'Prefer': 'count=exact',
        'Range': `${offset}-${offset + PAGE_SIZE - 1}`
    };

    try {
        const response = await fetch(url, { headers });
        if (!response.ok) throw new Error('Database request failed');

        const data = await response.json();
        
        // Extract total count from Content-Range header
        const contentRange = response.headers.get('Content-Range');
        if (contentRange && contentRange.includes('/')) {
            state.totalCount = parseInt(contentRange.split('/')[1]);
        } else {
            state.totalCount = data.length;
        }

        resultsCount.textContent = state.totalCount.toLocaleString();

        if (data.length === 0) {
            showLoader(false);
            emptyState.style.display = 'flex';
            return;
        }

        renderCards(data);
        updatePagination();
        showLoader(false);
        paginationContainer.style.display = 'flex';

    } catch (error) {
        console.error('Error fetching data:', error);
        showLoader(false);
        resultsCount.textContent = '0';
        emptyState.style.display = 'flex';
    }
}

function showLoader(show) {
    loader.style.display = show ? 'flex' : 'none';
}

function renderCards(persons) {
    resultsGrid.innerHTML = '';
    
    persons.forEach(person => {
        const card = document.createElement('div');
        card.className = 'person-card';

        // Avatar / Photo area
        let photoHtml = '';
        if (person.photo_url) {
            photoHtml = `<img src="${person.photo_url}" class="person-photo" alt="${person.name}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">`;
        }
        
        // Placeholder / Initials avatar
        const initials = person.name ? person.name.trim().charAt(0).toUpperCase() : '?';
        const placeholderHtml = `
            <div class="photo-placeholder" style="${person.photo_url ? 'display:none;' : ''}">
                <i class="fa-solid fa-user"></i>
                <div class="avatar-circle" style="
                    width: 50px; 
                    height: 50px; 
                    border-radius: 50%; 
                    background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%); 
                    color: white; 
                    display: flex; 
                    align-items: center; 
                    justify-content: center; 
                    font-size: 20px; 
                    font-weight: 700;
                    box-shadow: 0 4px 10px rgba(0,0,0,0.3);
                ">${initials}</div>
            </div>
        `;

        // Badges
        let statusBadge = person.status === 'found' 
            ? '<span class="badge badge-found">A Salvo</span>' 
            : '<span class="badge badge-missing">Desaparecido</span>';
            
        let childBadge = person.is_child 
            ? '<span class="badge badge-child">Menor de Edad</span>' 
            : '';

        // Formatted dates
        let dateStr = 'No disponible';
        if (person.ext_created) {
            const date = new Date(person.ext_created);
            dateStr = date.toLocaleDateString('es-VE', { 
                day: '2-digit', 
                month: 'short', 
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        }

        card.innerHTML = `
            <div class="card-header">
                ${photoHtml}
                ${placeholderHtml}
                <div class="badge-group">
                    ${statusBadge}
                    ${childBadge}
                </div>
            </div>
            <div class="card-body">
                <div class="person-info-main">
                    <h3 class="person-name" title="${person.name}">${person.name || 'Sin Nombre'}</h3>
                    ${person.age ? `<span class="person-age">${person.age} años</span>` : ''}
                </div>
                
                <div class="detail-item">
                    <i class="fa-solid fa-location-dot"></i>
                    <span class="detail-value">
                        <span class="detail-label">Visto por última vez:</span>
                        ${person.last_seen || 'No especificado'}
                    </span>
                </div>

                ${person.contact ? `
                <div class="detail-item">
                    <i class="fa-solid fa-phone"></i>
                    <span class="detail-value">
                        <span class="detail-label">Contacto:</span>
                        ${person.contact}
                    </span>
                </div>` : ''}

                <div class="detail-item">
                    <i class="fa-solid fa-clock"></i>
                    <span class="detail-value">
                        <span class="detail-label">Reportado:</span>
                        ${dateStr}
                    </span>
                </div>

                ${person.description ? `
                <p class="person-desc" title="${person.description}">
                    ${person.description}
                </p>` : ''}

                <div class="source-tag">
                    <i class="fa-solid fa-globe"></i> Origen: ${person.source || 'Red de Emergencia'}
                </div>
            </div>
        `;

        resultsGrid.appendChild(card);
    });
}

function updatePagination() {
    const maxPages = Math.ceil(state.totalCount / PAGE_SIZE);
    pageIndicator.textContent = `Página ${state.currentPage + 1} de ${Math.max(1, maxPages)}`;
    
    prevPageBtn.disabled = state.currentPage === 0;
    nextPageBtn.disabled = state.currentPage >= maxPages - 1 || maxPages === 0;
}

// Export data matching current filters to CSV
async function exportCSV() {
    const originalText = exportCsvBtn.innerHTML;
    exportCsvBtn.disabled = true;
    exportCsvBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generando CSV...';

    const url = buildQueryUrl(true);
    const headers = {
        'apikey': ANON_KEY,
        'Authorization': `Bearer ${ANON_KEY}`
    };

    try {
        const response = await fetch(url, { headers });
        if (!response.ok) throw new Error('Failed to fetch data for export');
        const data = await response.json();

        if (data.length === 0) {
            alert('No hay registros para exportar.');
            return;
        }

        // CSV headers
        const csvHeaders = ['Nombre', 'Edad', 'Menor de Edad', 'Última vez visto', 'Contacto', 'Estado', 'Descripción', 'Fecha Reporte', 'Origen', 'URL Foto', 'ID Registro'];
        
        let csvRows = [csvHeaders.join(',')];

        data.forEach(item => {
            const dateStr = item.ext_created ? new Date(item.ext_created).toISOString() : '';
            const row = [
                escapeCsvValue(item.name),
                item.age || '',
                item.is_child ? 'SÍ' : 'NO',
                escapeCsvValue(item.last_seen),
                escapeCsvValue(item.contact),
                item.status === 'found' ? 'Localizado/a salvo' : 'Desaparecido/a',
                escapeCsvValue(item.description),
                dateStr,
                escapeCsvValue(item.source),
                escapeCsvValue(item.photo_url),
                item.id
            ];
            csvRows.push(row.join(','));
        });

        const csvContent = "\ufeff" + csvRows.join('\n'); // Add BOM for Excel UTF-8 support
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const downloadUrl = URL.createObjectURL(blob);
        
        const link = document.createElement('a');
        link.setAttribute('href', downloadUrl);
        
        const timestamp = new Date().toISOString().slice(0, 10);
        const fileName = `red_ayuda_venezuela_${state.status}_${timestamp}.csv`;
        link.setAttribute('download', fileName);
        
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

    } catch (error) {
        console.error('Error exporting CSV:', error);
        alert('Ocurrió un error al intentar exportar los datos.');
    } finally {
        exportCsvBtn.disabled = false;
        exportCsvBtn.innerHTML = originalText;
    }
}

// Helper to escape values for CSV
function escapeCsvValue(val) {
    if (val === null || val === undefined) return '""';
    let text = String(val).replace(/"/g, '""'); // Escape double quotes
    return `"${text}"`;
}
