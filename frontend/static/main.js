// Function that runs once the window is fully loaded
window.onload = function() {
    var savedBaseUrl = localStorage.getItem('apiBaseUrl');
    if (savedBaseUrl) {
        document.getElementById('api-base-url').value = normalizeBaseUrl(savedBaseUrl);
        loadPosts();
    }
    if (localStorage.getItem('accessToken')) {
        setLoginStatus('Logged in (token saved)', true);
    }
}

function setLoginStatus(msg, ok) {
    var el = document.getElementById('login-status');
    if (el) { el.textContent = msg; el.className = 'login-status ' + (ok ? 'login-ok' : 'login-err'); }
}


function normalizeBaseUrl(raw) {
    var baseUrl = (raw || '').trim().replace(/\/+$/, '');

    // If the user entered ".../api", we force "/api/v1" to avoid a redirect that can drop Authorization on DELETE/PUT.
    if (baseUrl.endsWith('/api')) {
        baseUrl = baseUrl + '/v1';
    }

    return baseUrl;
}

function readBaseUrl() {
    var el = document.getElementById('api-base-url');
    var raw = (el && el.value) ? el.value : '';
    var normalized = normalizeBaseUrl(raw);
    if (el && el.value !== normalized) {
        el.value = normalized;
    }
    return normalized;
}


function getAuthHeaders() {
    var h = { 'Content-Type': 'application/json' };
    var token = localStorage.getItem('accessToken') || '';
    if (token) h['Authorization'] = 'Bearer ' + token;
    return h;
}

function login() {
    var baseUrl = (document.getElementById('api-base-url') && document.getElementById('api-base-url').value) || '';
    baseUrl = baseUrl.trim().replace(/\/+$/, '');
    var user = (document.getElementById('login-username') && document.getElementById('login-username').value) || '';
    var pw = (document.getElementById('login-password') && document.getElementById('login-password').value) || '';
    if (!user.trim() || !pw) {
        setLoginStatus('Enter username and password', false);
        return;
    }
    if (!baseUrl) {
        setLoginStatus('Enter API Base URL first', false);
        return;
    }
    var loginUrl = baseUrl + '/login';
    setLoginStatus('Logging in...', true);
    fetch(loginUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: user.trim(), password: pw })
    })
    .then(function(r) {
        return r.json().then(function(d) { return { ok: r.ok, status: r.status, data: d }; }).catch(function() {
            return { ok: false, status: r.status, data: { error: 'Server returned non-JSON (status ' + r.status + ')' } };
        });
    })
    .then(function(result) {
        if (result.ok && result.data.access_token) {
            localStorage.setItem('accessToken', result.data.access_token);
            setLoginStatus('Logged in as ' + (result.data.user && result.data.user.username || user), true);
        } else {
            setLoginStatus(result.data.error || 'Login failed (status ' + result.status + ')', false);
        }
    })
    .catch(function(err) {
        var msg = (err && err.message) ? err.message : String(err);
        console.error('Login request failed:', msg, 'URL:', loginUrl);
        if (msg.indexOf('fetch') !== -1 || msg.indexOf('Network') !== -1) {
            setLoginStatus('Network/CORS error – is the API running at ' + baseUrl + '?', false);
        } else {
            setLoginStatus('Login failed: ' + msg, false);
        }
    });
}

// Build the posts URL with optional search and sort query params
function getPostsUrl() {
    var baseUrl = readBaseUrl();
    var searchQuery = (document.getElementById('search-query') && document.getElementById('search-query').value) || '';
    var sortField = (document.getElementById('sort-field') && document.getElementById('sort-field').value) || '';
    var sortDirection = (document.getElementById('sort-direction') && document.getElementById('sort-direction').value) || 'asc';
    searchQuery = searchQuery.trim();

    if (searchQuery) {
        var searchParams = new URLSearchParams();
        searchParams.set('title', searchQuery);
        searchParams.set('content', searchQuery);
        return baseUrl + '/posts/search?' + searchParams.toString();
    }
    if (sortField) {
        return baseUrl + '/posts?sort=' + encodeURIComponent(sortField) + '&direction=' + encodeURIComponent(sortDirection);
    }
    return baseUrl + '/posts';
}

// Function to fetch all the posts from the API and display them on the page
function loadPosts() {
    var baseUrl = readBaseUrl();
    localStorage.setItem('apiBaseUrl', baseUrl);

    var url = getPostsUrl();
    fetch(url)
        .then(response => response.json())
        .then(data => {
            const postContainer = document.getElementById('post-container');
            postContainer.innerHTML = '';

            data.forEach(post => {
                const postDiv = document.createElement('div');
                postDiv.className = 'post';
                var author = (post.author !== undefined && post.author !== null) ? post.author : '';
                var date = (post.date !== undefined && post.date !== null) ? post.date : '';
                var meta = [author, date].filter(Boolean).join(' · ');
                if (meta) meta = '<div class="post-meta">' + escapeHtml(meta) + '</div>';
                postDiv.innerHTML = '<h2>' + escapeHtml(post.title) + '</h2>' + meta +
                    '<p>' + escapeHtml(post.content) + '</p>' +
                    '<button onclick="deletePost(' + post.id + ')">Delete</button>';
                postContainer.appendChild(postDiv);
            });
        })
        .catch(error => console.error('Error:', error));
}

function escapeHtml(text) {
    if (text == null) return '';
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Function to send a POST request to the API to add a new post
function addPost() {
    var baseUrl = readBaseUrl();
    var postTitle = document.getElementById('post-title').value;
    var postContent = document.getElementById('post-content').value;
    var postAuthor = (document.getElementById('post-author') && document.getElementById('post-author').value) || '';
    var postDate = (document.getElementById('post-date') && document.getElementById('post-date').value) || '';

    var body = { title: postTitle, content: postContent };
    if (postAuthor.trim()) body.author = postAuthor.trim();
    if (postDate.trim()) body.date = postDate.trim();

    var headers = getAuthHeaders();
    if (!headers.Authorization) {
        setLoginStatus('Please log in first (no token)', false);
        return;
    }
    fetch(baseUrl + '/posts', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(body)
    })
    .then(function(r) { return r.json().then(function(d) { return { status: r.status, data: d }; }); })
    .then(function(result) {
        if (result.status === 201) {
            loadPosts();
            setLoginStatus('Post created', true);
        } else if (result.status === 401) {
            if (result.data.error && result.data.error.indexOf('expired') !== -1) {
                localStorage.removeItem('accessToken');
                setLoginStatus('Session expired. Please log in again.', false);
            } else {
                setLoginStatus(result.data.error || 'Please log in to create posts', false);
            }
        } else {
            setLoginStatus('Error: ' + (result.data.error || result.status), false);
        }
    })
    .catch(error => console.error('Error:', error));
}

function deletePost(postId) {
    var baseUrl = readBaseUrl();
    var headers = getAuthHeaders();
    if (!headers.Authorization) {
        setLoginStatus('Please log in first (no token)', false);
        return;
    }
    fetch(baseUrl + '/posts/' + postId, {
        method: 'DELETE',
        headers: headers
    })
    .then(function(response) {
        return response.json().then(function(d) { return { status: response.status, data: d }; }).catch(function() { return { status: response.status, data: {} }; });
    })
    .then(function(result) {
        if (result.status === 200) {
            loadPosts();
        } else if (result.status === 401) {
            if (result.data.error && result.data.error.indexOf('expired') !== -1) {
                localStorage.removeItem('accessToken');
                setLoginStatus('Session expired. Please log in again.', false);
            } else {
                setLoginStatus(result.data.error || 'Please log in to delete', false);
            }
        } else {
            setLoginStatus('Error: ' + (result.data.error || result.status), false);
        }
    })
    .catch(error => console.error('Error:', error));
}
