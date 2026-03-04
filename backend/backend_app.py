import json
import os
import secrets
import sys
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
from flask_sqlalchemy import SQLAlchemy
from flask_swagger_ui import get_swaggerui_blueprint
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
# So the browser sends the Authorization header when frontend runs on a different origin (e.g. different port)
CORS(app, allow_headers=["Content-Type", "Authorization"], expose_headers=["Content-Type"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], supports_credentials=False)

# SQLAlchemy: SQLite database (default: data/masterblog.db in project root)
_basedir = os.path.dirname(os.path.abspath(__file__))
_data_dir = os.path.join(_basedir, "..", "data")
_default_db = os.path.join(_data_dir, "masterblog.db")
_default_uri = "sqlite:///" + os.path.abspath(_default_db).replace("\\", "/")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URI", _default_uri)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


def _get_jwt_secret():
    """Use JWT_SECRET_KEY from env, or a persistent file so the same key is used across restarts/reloads."""
    key = os.environ.get("JWT_SECRET_KEY")
    if key:
        return key
    secret_file = os.path.join(_data_dir, ".jwt_secret")
    if os.path.exists(secret_file):
        with open(secret_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    os.makedirs(_data_dir, exist_ok=True)
    key = secrets.token_hex(32)
    with open(secret_file, "w", encoding="utf-8") as f:
        f.write(key)
    return key

# Swagger UI – API docs at http://localhost:5002/api/docs
SWAGGER_URL = "/api/docs"
API_URL = "/static/masterblog.json"
swagger_ui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={"app_name": "Masterblog API"},
)
app.register_blueprint(swagger_ui_blueprint, url_prefix=SWAGGER_URL)

# Min 32 bytes for HMAC-SHA256; use persistent file so token works across restarts and reloader
app.config["JWT_SECRET_KEY"] = _get_jwt_secret()
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 86400))  # 24h default
# Read token from: Authorization: Bearer <token> (default; set explicitly for clarity)
app.config["JWT_HEADER_NAME"] = "Authorization"
app.config["JWT_HEADER_TYPE"] = "Bearer"
jwt = JWTManager(app)


@jwt.unauthorized_loader
def unauthorized_callback(_):
    return jsonify({"error": "Authorization required. Missing or invalid token."}), 401


@jwt.invalid_token_loader
def invalid_token_callback(err):
    if app.debug:
        auth = request.headers.get("Authorization") or ""
        token_preview = auth[:20] + "..." if len(auth) > 20 else auth
        app.logger.warning("JWT invalid/expired: %s | Auth header length=%s prefix=%r", err, len(auth), token_preview)
    return jsonify({"error": "Invalid or expired token."}), 401

# Rate limiting: per IP, default 100 requests/minute (configurable)
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["100 per minute"],
    storage_uri="memory://",
)

# API versioning: v1 blueprint (e.g. /api/v2 for breaking changes later)
api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")


class Post(db.Model):
    """Blog post, persisted in the database."""
    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(500), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(200), default="")
    date = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD
    category_ids = db.Column(db.Text, default="[]")  # JSON list
    tag_ids = db.Column(db.Text, default="[]")       # JSON list

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "author": self.author or "",
            "date": self.date or "",
            "category_ids": json.loads(self.category_ids) if self.category_ids else [],
            "tag_ids": json.loads(self.tag_ids) if self.tag_ids else [],
        }


class User(db.Model):
    """User for auth, persisted in the database."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


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


def _get_all_posts_as_dicts():
    """Return all posts from the DB as a list of dicts (for _enrich_post)."""
    return [p.to_dict() for p in Post.query.all()]


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

def _user_by_id(uid):
    if uid is None:
        return None
    u = User.query.get(int(uid))
    if u is None:
        return None
    return {"id": u.id, "username": u.username}


def _enrich_post(post):
    """Add resolved categories and tags to the post (for response)."""
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
    """Apply optional pagination. Returns (sliced_list, total, page, limit)."""
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


# ---------- Auth: registration & login ----------

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

    existing = User.query.filter(db.func.lower(User.username) == username.lower()).first()
    if existing:
        return jsonify({"error": "Username already taken"}), 409

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({"id": user.id, "username": user.username}), 201


@api_v1.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    username = (data.get("username") or "").strip()
    password = data.get("password")

    if not username or password is None:
        return jsonify({"error": "Username and password are required"}), 400

    user = User.query.filter(db.func.lower(User.username) == username.lower()).first()
    if user and check_password_hash(user.password_hash, password):
        access_token = create_access_token(identity=str(user.id))
        return jsonify({
            "access_token": access_token,
            "user": {"id": user.id, "username": user.username},
        }), 200

    return jsonify({"error": "Invalid username or password"}), 401


@api_v1.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Return the current user from the JWT. Use this in Postman to verify the token works."""
    uid = get_jwt_identity()
    user = User.query.get(int(uid))
    if user is None:
        return jsonify({"error": "User not found."}), 404
    return jsonify({"id": user.id, "username": user.username}), 200


# ---------- Posts (public: list, search) ----------

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

    posts = _get_all_posts_as_dicts()
    if sort:
        if sort == 'date':
            posts = sorted(posts, key=_date_sort_key, reverse=(direction == 'desc'))
        else:
            posts = sorted(posts, key=lambda p: (p.get(sort) or "").lower(), reverse=(direction == 'desc'))

    # Optional: filter by category or tag
    category_id = request.args.get('category_id', type=int)
    tag_id = request.args.get('tag_id', type=int)
    if category_id is not None:
        posts = [p for p in posts if category_id in p.get("category_ids", [])]
    if tag_id is not None:
        posts = [p for p in posts if tag_id in p.get("tag_ids", [])]

    sliced, total, page, limit = _apply_pagination(posts)
    if sliced is None:
        return jsonify({"error": limit}), 400  # limit holds the error message here

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

    posts = _get_all_posts_as_dicts()
    if not title_q and not content_q and not author_q and not date_q:
        results = posts
    else:
        results = []
        for post in posts:
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
    post = Post.query.get(post_id)
    if post is None:
        return jsonify({"error": "Post not found"}), 404
    comments = [_enrich_comment(c) for c in COMMENTS if c["post_id"] == post_id]
    out = _enrich_post(post.to_dict())
    out["comments"] = comments
    return jsonify(out), 200


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

    new_post = Post(
        title=data["title"],
        content=data["content"],
        author=author,
        date=date_str,
        category_ids=json.dumps(category_ids),
        tag_ids=json.dumps(tag_ids),
    )
    db.session.add(new_post)
    db.session.commit()
    return jsonify(_enrich_post(new_post.to_dict())), 201


@api_v1.route('/posts/<int:post_id>', methods=['DELETE'])
@jwt_required()
def delete_post(post_id):
    post = Post.query.get(post_id)
    if post is None:
        return jsonify({"error": "Post not found"}), 404
    db.session.delete(post)
    db.session.commit()
    global COMMENTS
    COMMENTS = [c for c in COMMENTS if c["post_id"] != post_id]
    return jsonify({"message": f"Post with id {post_id} has been deleted successfully."}), 200


@api_v1.route('/posts/<int:post_id>', methods=['PUT'])
@jwt_required()
def update_post(post_id):
    data = request.get_json(silent=True) or {}
    post = Post.query.get(post_id)
    if post is None:
        return jsonify({"error": "Post not found"}), 404

    if "title" in data:
        post.title = data["title"]
    if "content" in data:
        post.content = data["content"]
    if "author" in data:
        post.author = (data["author"] or "").strip() if data["author"] is not None else ""
    if "date" in data:
        date_str = (data.get("date") or "").strip()
        if date_str:
            parsed = _parse_date(date_str)
            if parsed is None:
                return jsonify({"error": "date must be in YYYY-MM-DD format"}), 400
            post.date = parsed.strftime("%Y-%m-%d")
        else:
            post.date = date.today().strftime("%Y-%m-%d")
    if "category_ids" in data:
        ids = data["category_ids"]
        if not isinstance(ids, list) or not all(isinstance(x, int) for x in ids):
            return jsonify({"error": "category_ids must be a list of integers"}), 400
        if not all(any(c["id"] == x for c in CATEGORIES) for x in ids):
            return jsonify({"error": "One or more category_ids are invalid"}), 400
        post.category_ids = json.dumps(ids)
    if "tag_ids" in data:
        ids = data["tag_ids"]
        if not isinstance(ids, list) or not all(isinstance(x, int) for x in ids):
            return jsonify({"error": "tag_ids must be a list of integers"}), 400
        if not all(any(t["id"] == x for t in TAGS) for x in ids):
            return jsonify({"error": "One or more tag_ids are invalid"}), 400
        post.tag_ids = json.dumps(ids)
    db.session.commit()
    return jsonify(_enrich_post(post.to_dict())), 200


# ---------- Categories ----------

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


# ---------- Comments ----------

@api_v1.route('/posts/<int:post_id>/comments', methods=['GET'])
def list_comments(post_id):
    if Post.query.get(post_id) is None:
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
    if Post.query.get(post_id) is None:
        return jsonify({"error": "Post not found"}), 404
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Content is required"}), 400
    global _NEXT_COMMENT_ID, COMMENTS
    author_id = int(get_jwt_identity())
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


# Rate limit exceeded: consistent JSON response
@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Too many requests. Please try again later."}), 429


# Backward compatibility: /api/... maps to /api/v1/... without redirects.
# Browsers may drop Authorization headers on redirected DELETE/PUT requests; aliases avoid that class of issues.
@app.route("/api/register", methods=["POST"])
def legacy_register():
    return register()


@app.route("/api/login", methods=["POST"])
def legacy_login():
    return login()


@app.route("/api/posts", methods=["GET", "POST"])
def legacy_posts():
    if request.method == "GET":
        return get_posts()
    return add_post()


@app.route("/api/posts/search", methods=["GET"])
def legacy_search_posts():
    return search_posts()


@app.route("/api/posts/<int:post_id>", methods=["GET", "DELETE", "PUT"])
def legacy_post(post_id):
    if request.method == "GET":
        return get_post(post_id)
    if request.method == "DELETE":
        return delete_post(post_id)
    return update_post(post_id)


@app.route("/api/categories", methods=["GET", "POST"])
def legacy_categories():
    if request.method == "GET":
        return list_categories()
    return create_category()


@app.route("/api/tags", methods=["GET", "POST"])
def legacy_tags():
    if request.method == "GET":
        return list_tags()
    return create_tag()


@app.route("/api/posts/<int:post_id>/comments", methods=["GET", "POST"])
def legacy_comments(post_id):
    if request.method == "GET":
        return list_comments(post_id)
    return create_comment(post_id)


if __name__ == '__main__':
    _backend_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(_backend_dir)
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from backend import init_db as _init_db
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if uri.startswith("sqlite:///"):
        db_path = uri.replace("sqlite:///", "")
        if db_path and not os.path.exists(db_path):
            _init_db.ensure_db_exists()
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5002, debug=True)
