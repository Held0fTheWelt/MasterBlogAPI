import os
from datetime import date, datetime
from flask import Blueprint, Flask, jsonify, redirect, request
from flask_cors import CORS
from flask_jwt_extended import (
    create_access_token,
    get_jwt_identity,
    jwt_required,
    JWTManager,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_swagger_ui import get_swaggerui_blueprint
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
CORS(app)

# Swagger UI – API-Dokumentation unter http://localhost:5002/api/docs
SWAGGER_URL = "/api/docs"
API_URL = "/static/masterblog.json"
swagger_ui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={"app_name": "Masterblog API"},
)
app.register_blueprint(swagger_ui_blueprint, url_prefix=SWAGGER_URL)

app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "change-me-in-production")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 3600))  # 1h
jwt = JWTManager(app)


@jwt.unauthorized_loader
def unauthorized_callback(_):
    return jsonify({"error": "Authorization required. Missing or invalid token."}), 401


@jwt.invalid_token_loader
def invalid_token_callback(_):
    return jsonify({"error": "Invalid or expired token."}), 401

# Rate limiting: pro IP, Standard 100 Requests/Minute (konfigurierbar)
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["100 per minute"],
    storage_uri="memory://",
)

# API Versioning: v1 Blueprint (später z. B. /api/v2 für Breaking Changes)
api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")

def _parse_date(s):
    """Parse YYYY-MM-DD string to date; return None if invalid."""
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _date_sort_key(post):
    """Sort key for date field: use parsed date for correct ordering."""
    d = _parse_date(post.get("date") or "")
    return d if d is not None else date.min


POSTS = [
    {
        "id": 1,
        "title": "First post",
        "content": "This is the first post.",
        "author": "Admin",
        "date": "2023-06-07",
        "category_ids": [1],
        "tag_ids": [1, 2],
    },
    {
        "id": 2,
        "title": "Second post",
        "content": "This is the second post.",
        "author": "Admin",
        "date": "2023-06-08",
        "category_ids": [2],
        "tag_ids": [2],
    },
]

CATEGORIES = [
    {"id": 1, "name": "Tech"},
    {"id": 2, "name": "Life"},
]
_NEXT_CATEGORY_ID = 3

TAGS = [
    {"id": 1, "name": "python"},
    {"id": 2, "name": "flask"},
]
_NEXT_TAG_ID = 3

COMMENTS = [
    {"id": 1, "post_id": 1, "author_id": None, "content": "First comment.", "created_at": "2024-01-01T12:00:00"},
]
_NEXT_COMMENT_ID = 2

# User-Speicher (In-Memory). In Produktion: Datenbank + sichere Secrets.
USERS = []
_NEXT_USER_ID = 1


def _user_by_id(uid):
    for u in USERS:
        if u["id"] == uid:
            return u
    return None


def _enrich_post(post):
    """Fügt aufgelöste Kategorien und Tags zum Post hinzu (für Response)."""
    out = dict(post)
    out["categories"] = [c for c in CATEGORIES if c["id"] in post.get("category_ids", [])]
    out["tags"] = [t for t in TAGS if t["id"] in post.get("tag_ids", [])]
    return out


def _enrich_comment(comment):
    out = dict(comment)
    u = _user_by_id(comment.get("author_id"))
    out["author_name"] = u["username"] if u else "(anonymous)"
    return out


def _apply_pagination(items, default_limit=None, max_limit=100):
    """Wendet optionale Pagination an. Gibt (slice_list, total, page, limit) zurück."""
    page_arg = request.args.get('page', type=int)
    limit_arg = request.args.get('limit', type=int)

    if limit_arg is None and page_arg is None:
        return items, len(items), None, None

    limit = limit_arg if limit_arg is not None else (default_limit or 10)
    page = page_arg if page_arg is not None else 1

    if limit < 1:
        return None, None, None, "limit must be at least 1"
    if limit > max_limit:
        return None, None, None, f"limit must be at most {max_limit}"
    if page < 1:
        return None, None, None, "page must be at least 1"

    total = len(items)
    start = (page - 1) * limit
    end = start + limit
    return items[start:end], total, page, limit


# ---------- Auth: Registrierung & Login ----------

@api_v1.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    username = (data.get("username") or "").strip()
    password = data.get("password")

    if not username:
        return jsonify({"error": "Username is required"}), 400
    if not password:
        return jsonify({"error": "Password is required"}), 400
    if len(username) < 2:
        return jsonify({"error": "Username must be at least 2 characters"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    for u in USERS:
        if u["username"].lower() == username.lower():
            return jsonify({"error": "Username already taken"}), 409

    global _NEXT_USER_ID
    user_id = _NEXT_USER_ID
    _NEXT_USER_ID += 1
    user = {
        "id": user_id,
        "username": username,
        "password_hash": generate_password_hash(password),
    }
    USERS.append(user)
    return jsonify({"id": user_id, "username": username}), 201


@api_v1.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    username = (data.get("username") or "").strip()
    password = data.get("password")

    if not username or password is None:
        return jsonify({"error": "Username and password are required"}), 400

    for u in USERS:
        if u["username"].lower() == username.lower() and check_password_hash(u["password_hash"], password):
            access_token = create_access_token(identity=u["id"])
            return jsonify({
                "access_token": access_token,
                "user": {"id": u["id"], "username": u["username"]},
            }), 200

    return jsonify({"error": "Invalid username or password"}), 401


# ---------- Posts (öffentlich: List, Search) ----------

@api_v1.route('/posts', methods=['GET'])
def get_posts():
    sort = request.args.get('sort', '').strip().lower()
    direction = request.args.get('direction', '').strip().lower()

    if sort and sort not in ('title', 'content', 'author', 'date'):
        return jsonify({"error": "Invalid sort field. Must be 'title', 'content', 'author' or 'date'."}), 400
    if direction and direction not in ('asc', 'desc'):
        return jsonify({"error": "Invalid direction. Must be 'asc' or 'desc'."}), 400
    if direction and not sort:
        return jsonify({"error": "Parameter 'sort' is required when 'direction' is provided."}), 400

    if sort:
        if sort == 'date':
            posts = sorted(POSTS, key=_date_sort_key, reverse=(direction == 'desc'))
        else:
            posts = sorted(POSTS, key=lambda p: (p.get(sort) or "").lower(), reverse=(direction == 'desc'))
    else:
        posts = list(POSTS)

    # Optional: nach Kategorie oder Tag filtern
    category_id = request.args.get('category_id', type=int)
    tag_id = request.args.get('tag_id', type=int)
    if category_id is not None:
        posts = [p for p in posts if category_id in p.get("category_ids", [])]
    if tag_id is not None:
        posts = [p for p in posts if tag_id in p.get("tag_ids", [])]

    sliced, total, page, limit = _apply_pagination(posts)
    if sliced is None:
        return jsonify({"error": limit}), 400  # limit ist hier die Fehlermeldung

    if page is not None:
        resp = jsonify([_enrich_post(p) for p in sliced])
        resp.headers['X-Total-Count'] = str(total)
        resp.headers['X-Page'] = str(page)
        resp.headers['X-Per-Page'] = str(limit)
        return resp
    return jsonify([_enrich_post(p) for p in sliced])


@api_v1.route('/posts/search', methods=['GET'])
def search_posts():
    title_q = request.args.get('title', '').lower()
    content_q = request.args.get('content', '').lower()
    author_q = request.args.get('author', '').lower()
    date_q = request.args.get('date', '').strip()

    if not title_q and not content_q and not author_q and not date_q:
        results = list(POSTS)
    else:
        results = []
        for post in POSTS:
            title_match = title_q in (post.get('title') or '').lower() if title_q else False
            content_match = content_q in (post.get('content') or '').lower() if content_q else False
            author_match = author_q in (post.get('author') or '').lower() if author_q else False
            date_str = (post.get('date') or '')[:10]
            date_match = date_q in date_str if date_q else False
            if title_match or content_match or author_match or date_match:
                results.append(post)

    category_id = request.args.get('category_id', type=int)
    tag_id = request.args.get('tag_id', type=int)
    if category_id is not None:
        results = [p for p in results if category_id in p.get("category_ids", [])]
    if tag_id is not None:
        results = [p for p in results if tag_id in p.get("tag_ids", [])]

    sliced, total, page, limit = _apply_pagination(results)
    if sliced is None:
        return jsonify({"error": limit}), 400
    if page is not None:
        resp = jsonify([_enrich_post(p) for p in sliced])
        resp.headers['X-Total-Count'] = str(total)
        resp.headers['X-Page'] = str(page)
        resp.headers['X-Per-Page'] = str(limit)
        return resp
    return jsonify([_enrich_post(p) for p in sliced])


@api_v1.route('/posts/<int:post_id>', methods=['GET'])
def get_post(post_id):
    for post in POSTS:
        if post["id"] == post_id:
            comments = [_enrich_comment(c) for c in COMMENTS if c["post_id"] == post_id]
            out = _enrich_post(post)
            out["comments"] = comments
            return jsonify(out), 200
    return jsonify({"error": "Post not found"}), 404


@api_v1.route('/posts', methods=['POST'])
@jwt_required()
def add_post():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    missing = []
    if not data.get("title"):
        missing.append("title")
    if not data.get("content"):
        missing.append("content")

    if missing:
        return jsonify({"error": f"Missing required field(s): {', '.join(missing)}"}), 400

    author = (data.get("author") or "").strip() if data.get("author") is not None else ""
    date_str = (data.get("date") or "").strip()
    if date_str:
        parsed = _parse_date(date_str)
        if parsed is None:
            return jsonify({"error": "date must be in YYYY-MM-DD format"}), 400
        date_str = parsed.strftime("%Y-%m-%d")
    else:
        date_str = date.today().strftime("%Y-%m-%d")

    category_ids = data.get("category_ids") or []
    tag_ids = data.get("tag_ids") or []
    if not isinstance(category_ids, list) or not all(isinstance(x, int) for x in category_ids):
        return jsonify({"error": "category_ids must be a list of integers"}), 400
    if not isinstance(tag_ids, list) or not all(isinstance(x, int) for x in tag_ids):
        return jsonify({"error": "tag_ids must be a list of integers"}), 400
    cat_ok = all(any(c["id"] == x for c in CATEGORIES) for x in category_ids)
    tag_ok = all(any(t["id"] == x for t in TAGS) for x in tag_ids)
    if not cat_ok:
        return jsonify({"error": "One or more category_ids are invalid"}), 400
    if not tag_ok:
        return jsonify({"error": "One or more tag_ids are invalid"}), 400

    new_id = max((p["id"] for p in POSTS), default=0) + 1
    new_post = {
        "id": new_id,
        "title": data["title"],
        "content": data["content"],
        "author": author,
        "date": date_str,
        "category_ids": category_ids,
        "tag_ids": tag_ids,
    }
    POSTS.append(new_post)
    return jsonify(_enrich_post(new_post)), 201


@api_v1.route('/posts/<int:post_id>', methods=['DELETE'])
@jwt_required()
def delete_post(post_id):
    for i, post in enumerate(POSTS):
        if post["id"] == post_id:
            POSTS.pop(i)
            # Kommentare zu diesem Post entfernen
            global COMMENTS
            COMMENTS = [c for c in COMMENTS if c["post_id"] != post_id]
            return jsonify({"message": f"Post with id {post_id} has been deleted successfully."}), 200
    return jsonify({"error": "Post not found"}), 404


@api_v1.route('/posts/<int:post_id>', methods=['PUT'])
@jwt_required()
def update_post(post_id):
    data = request.get_json(silent=True) or {}

    for post in POSTS:
        if post["id"] == post_id:
            if "title" in data:
                post["title"] = data["title"]
            if "content" in data:
                post["content"] = data["content"]
            if "author" in data:
                post["author"] = (data["author"] or "").strip() if data["author"] is not None else ""
            if "date" in data:
                date_str = (data.get("date") or "").strip()
                if date_str:
                    parsed = _parse_date(date_str)
                    if parsed is None:
                        return jsonify({"error": "date must be in YYYY-MM-DD format"}), 400
                    post["date"] = parsed.strftime("%Y-%m-%d")
                else:
                    post["date"] = date.today().strftime("%Y-%m-%d")
            if "category_ids" in data:
                ids = data["category_ids"]
                if not isinstance(ids, list) or not all(isinstance(x, int) for x in ids):
                    return jsonify({"error": "category_ids must be a list of integers"}), 400
                if not all(any(c["id"] == x for c in CATEGORIES) for x in ids):
                    return jsonify({"error": "One or more category_ids are invalid"}), 400
                post["category_ids"] = ids
            if "tag_ids" in data:
                ids = data["tag_ids"]
                if not isinstance(ids, list) or not all(isinstance(x, int) for x in ids):
                    return jsonify({"error": "tag_ids must be a list of integers"}), 400
                if not all(any(t["id"] == x for t in TAGS) for x in ids):
                    return jsonify({"error": "One or more tag_ids are invalid"}), 400
                post["tag_ids"] = ids
            return jsonify(_enrich_post(post)), 200

    return jsonify({"error": "Post not found"}), 404


# ---------- Kategorien ----------

@api_v1.route('/categories', methods=['GET'])
def list_categories():
    return jsonify(CATEGORIES), 200


@api_v1.route('/categories', methods=['POST'])
@jwt_required()
def create_category():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    if any(c["name"].lower() == name.lower() for c in CATEGORIES):
        return jsonify({"error": "Category with this name already exists"}), 409
    global _NEXT_CATEGORY_ID
    cat = {"id": _NEXT_CATEGORY_ID, "name": name}
    _NEXT_CATEGORY_ID += 1
    CATEGORIES.append(cat)
    return jsonify(cat), 201


# ---------- Tags ----------

@api_v1.route('/tags', methods=['GET'])
def list_tags():
    return jsonify(TAGS), 200


@api_v1.route('/tags', methods=['POST'])
@jwt_required()
def create_tag():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    if any(t["name"].lower() == name.lower() for t in TAGS):
        return jsonify({"error": "Tag with this name already exists"}), 409
    global _NEXT_TAG_ID
    tag = {"id": _NEXT_TAG_ID, "name": name}
    _NEXT_TAG_ID += 1
    TAGS.append(tag)
    return jsonify(tag), 201


# ---------- Kommentare ----------

@api_v1.route('/posts/<int:post_id>/comments', methods=['GET'])
def list_comments(post_id):
    if not any(p["id"] == post_id for p in POSTS):
        return jsonify({"error": "Post not found"}), 404
    comments = [_enrich_comment(c) for c in COMMENTS if c["post_id"] == post_id]
    sliced, total, page, limit = _apply_pagination(comments)
    if sliced is None:
        return jsonify({"error": limit}), 400
    if page is not None:
        resp = jsonify(sliced)
        resp.headers['X-Total-Count'] = str(total)
        resp.headers['X-Page'] = str(page)
        resp.headers['X-Per-Page'] = str(limit)
        return resp
    return jsonify(sliced)


@api_v1.route('/posts/<int:post_id>/comments', methods=['POST'])
@jwt_required()
def create_comment(post_id):
    if not any(p["id"] == post_id for p in POSTS):
        return jsonify({"error": "Post not found"}), 404
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Content is required"}), 400
    global _NEXT_COMMENT_ID, COMMENTS
    author_id = get_jwt_identity()
    comment = {
        "id": _NEXT_COMMENT_ID,
        "post_id": post_id,
        "author_id": author_id,
        "content": content,
        "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _NEXT_COMMENT_ID += 1
    COMMENTS.append(comment)
    return jsonify(_enrich_comment(comment)), 201


app.register_blueprint(api_v1)


# Rate-Limit-Überschreitung: einheitliche JSON-Antwort
@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Too many requests. Please try again later."}), 429


# Abwärtskompatibilität: /api/register, /api/login → /api/v1/...
@app.route("/api/register", methods=["POST"])
@app.route("/api/login", methods=["POST"])
def redirect_api_auth_to_v1():
    path = request.path.replace("/api/", "/api/v1/", 1)
    return redirect(path, code=307)


# Abwärtskompatibilität: /api/posts* → /api/v1/posts* (307 = Method + Body bleiben)
@app.route("/api/posts", methods=["GET", "POST"])
@app.route("/api/posts/search", methods=["GET"])
def redirect_api_posts_to_v1():
    path = request.path.replace("/api/", "/api/v1/", 1)
    if request.query_string:
        path = f"{path}?{request.query_string.decode()}"
    return redirect(path, code=307)


@app.route("/api/posts/<int:post_id>", methods=["DELETE", "PUT"])
def redirect_api_post_to_v1(post_id):
    path = f"/api/v1/posts/{post_id}"
    if request.query_string:
        path = f"{path}?{request.query_string.decode()}"
    return redirect(path, code=307)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5002, debug=True)
