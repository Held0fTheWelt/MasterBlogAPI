from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # This will enable CORS for all routes

POSTS = [
    {"id": 1, "title": "First post", "content": "This is the first post."},
    {"id": 2, "title": "Second post", "content": "This is the second post."},
]


@app.route('/api/posts', methods=['GET'])
def get_posts():
    sort = request.args.get('sort', '').strip().lower()
    direction = request.args.get('direction', '').strip().lower()

    if not sort and not direction:
        return jsonify(POSTS)

    if sort and sort not in ('title', 'content'):
        return jsonify({"error": "Invalid sort field. Must be 'title' or 'content'."}), 400
    if direction and direction not in ('asc', 'desc'):
        return jsonify({"error": "Invalid direction. Must be 'asc' or 'desc'."}), 400
    if direction and not sort:
        return jsonify({"error": "Parameter 'sort' is required when 'direction' is provided."}), 400

    if not sort:
        return jsonify(POSTS)

    sorted_posts = sorted(POSTS, key=lambda p: p[sort].lower(), reverse=(direction == 'desc'))
    return jsonify(sorted_posts)


@app.route('/api/posts/search', methods=['GET'])
def search_posts():
    title_q = request.args.get('title', '').lower()
    content_q = request.args.get('content', '').lower()

    # Wenn keine Suchbegriffe übergeben wurden, alle Posts zurückgeben
    if not title_q and not content_q:
        return jsonify(POSTS)

    results = []
    for post in POSTS:
        title_match = title_q in post['title'].lower() if title_q else False
        content_match = content_q in post['content'].lower() if content_q else False

        if title_match or content_match:
            results.append(post)

    return jsonify(results)


@app.route('/api/posts', methods=['POST'])
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


@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    for i, post in enumerate(POSTS):
        if post["id"] == post_id:
            POSTS.pop(i)
            return jsonify({"message": f"Post with id {post_id} has been deleted successfully."}), 200
    return jsonify({"error": "Post not found"}), 404


@app.route('/api/posts/<int:post_id>', methods=['PUT'])
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


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5002, debug=True)
