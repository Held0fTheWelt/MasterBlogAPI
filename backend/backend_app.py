import os
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
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
CORS(app)

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

POSTS = [
    {"id": 1, "title": "First post", "content": "This is the first post."},
    {"id": 2, "title": "Second post", "content": "This is the second post."},
]

# User-Speicher (In-Memory). In Produktion: Datenbank + sichere Secrets.
USERS = []
_NEXT_USER_ID = 1


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

    if sort and sort not in ('title', 'content'):
        return jsonify({"error": "Invalid sort field. Must be 'title' or 'content'."}), 400
    if direction and direction not in ('asc', 'desc'):
        return jsonify({"error": "Invalid direction. Must be 'asc' or 'desc'."}), 400
    if direction and not sort:
        return jsonify({"error": "Parameter 'sort' is required when 'direction' is provided."}), 400

    if sort:
        posts = sorted(POSTS, key=lambda p: p[sort].lower(), reverse=(direction == 'desc'))
    else:
        posts = POSTS

    sliced, total, page, limit = _apply_pagination(posts)
    if sliced is None:
        return jsonify({"error": limit}), 400  # limit ist hier die Fehlermeldung

    if page is not None:
        resp = jsonify(sliced)
        resp.headers['X-Total-Count'] = str(total)
        resp.headers['X-Page'] = str(page)
        resp.headers['X-Per-Page'] = str(limit)
        return resp
    return jsonify(sliced)


@api_v1.route('/posts/search', methods=['GET'])
def search_posts():
    title_q = request.args.get('title', '').lower()
    content_q = request.args.get('content', '').lower()

    if not title_q and not content_q:
        results = list(POSTS)
    else:
        results = []
        for post in POSTS:
            title_match = title_q in post['title'].lower() if title_q else False
            content_match = content_q in post['content'].lower() if content_q else False
            if title_match or content_match:
                results.append(post)

    sliced, total, page, limit = _apply_pagination(results)
    if sliced is None:
        return jsonify({"error": limit}), 400
    if page is not None:
        resp = jsonify(sliced)
        resp.headers['X-Total-Count'] = str(total)
        resp.headers['X-Page'] = str(page)
        resp.headers['X-Per-Page'] = str(limit)
        return resp
    return jsonify(sliced)


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

    new_id = max((p["id"] for p in POSTS), default=0) + 1
    new_post = {"id": new_id, "title": data["title"], "content": data["content"]}
    POSTS.append(new_post)
    return jsonify(new_post), 201


@api_v1.route('/posts/<int:post_id>', methods=['DELETE'])
@jwt_required()
def delete_post(post_id):
    for i, post in enumerate(POSTS):
        if post["id"] == post_id:
            POSTS.pop(i)
            return jsonify({"message": f"Post with id {post_id} has been deleted successfully."}), 200
    return jsonify({"error": "Post not found"}), 404


@api_v1.route('/posts/<int:post_id>', methods=['PUT'])
@jwt_required()
def update_post(post_id):
    data = request.get_json(silent=True) or {}

    for post in POSTS:
        if post["id"] == post_id:
            # Nur Felder aktualisieren, die im Body vorhanden sind
            if "title" in data:
                post["title"] = data["title"]
            if "content" in data:
                post["content"] = data["content"]
            return jsonify(post), 200

    return jsonify({"error": "Post not found"}), 404


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
