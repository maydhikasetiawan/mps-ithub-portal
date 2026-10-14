from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort
from routes.auth import login_required, roles_required
from database.db import get_db_connection

knowledge_base_bp = Blueprint('knowledge_base', __name__, url_prefix='/knowledge-base')


@knowledge_base_bp.route('/')
@login_required
@roles_required('admin', 'it', 'user', 'guest')
def index():
    user_role = session.get('role', 'guest')
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if user_role in ['admin', 'it']:
            cur.execute("SELECT * FROM kb_articles ORDER BY created_at DESC;")
        else:
            cur.execute("SELECT * FROM kb_articles WHERE status = 'published' ORDER BY created_at DESC;")
        articles = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return render_template('knowledge_base/list.html', articles=articles, active_page='knowledge_base')


@knowledge_base_bp.route('/<int:article_id>')
@login_required
@roles_required('admin', 'it', 'user', 'guest')
def detail(article_id):
    user_role = session.get('role', 'guest')
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM kb_articles WHERE id = %s;", (article_id,))
        article = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not article:
        abort(404)

    # Draft articles visible to admin/it only; 404 for others to avoid leaking draft existence
    if article['status'] == 'draft' and user_role not in ['admin', 'it']:
        abort(404)

    return render_template('knowledge_base/detail.html', article=article, active_page='knowledge_base')


@knowledge_base_bp.route('/add', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'it')
def add():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM ticket_categories ORDER BY name ASC;")
        categories = cur.fetchall()
        valid_categories = {c['name'] for c in categories}

        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            category = request.form.get('category', '').strip()
            tags = request.form.get('tags', '').strip()
            content = request.form.get('content', '').strip()
            status = request.form.get('status', '').strip().lower()

            if not title:
                flash("Judul artikel tidak boleh kosong.", "danger")
            elif not content:
                flash("Konten artikel tidak boleh kosong.", "danger")
            elif category not in valid_categories:
                flash("Kategori tidak valid.", "danger")
            elif status not in ['draft', 'published']:
                flash("Status harus draft atau published.", "danger")
            else:
                author = session.get('username')
                cur.execute("""
                    INSERT INTO kb_articles (title, category, content, tags, status, author)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (title, category, content, tags if tags else None, status, author))
                new_id = cur.fetchone()['id']
                conn.commit()
                flash("Artikel berhasil ditambahkan!", "success")
                return redirect(url_for('knowledge_base.detail', article_id=new_id))

            article_data = {
                'title': title,
                'category': category,
                'tags': tags,
                'content': content,
                'status': status
            }
            return render_template(
                'knowledge_base/form.html',
                article=article_data,
                categories=categories,
                is_edit=False,
                active_page='knowledge_base'
            )

        return render_template(
            'knowledge_base/form.html',
            article=None,
            categories=categories,
            is_edit=False,
            active_page='knowledge_base'
        )
    finally:
        cur.close()
        conn.close()


@knowledge_base_bp.route('/<int:article_id>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'it')
def edit(article_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM kb_articles WHERE id = %s;", (article_id,))
        article = cur.fetchone()
        if not article:
            abort(404)

        cur.execute("SELECT name FROM ticket_categories ORDER BY name ASC;")
        categories = cur.fetchall()
        valid_categories = {c['name'] for c in categories}

        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            category = request.form.get('category', '').strip()
            tags = request.form.get('tags', '').strip()
            content = request.form.get('content', '').strip()
            status = request.form.get('status', '').strip().lower()

            if not title:
                flash("Judul artikel tidak boleh kosong.", "danger")
            elif not content:
                flash("Konten artikel tidak boleh kosong.", "danger")
            elif category not in valid_categories:
                flash("Kategori tidak valid.", "danger")
            elif status not in ['draft', 'published']:
                flash("Status harus draft atau published.", "danger")
            else:
                cur.execute("""
                    UPDATE kb_articles
                    SET title = %s, category = %s, content = %s, tags = %s, status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s;
                """, (title, category, content, tags if tags else None, status, article_id))
                conn.commit()
                flash("Artikel berhasil diperbarui!", "success")
                return redirect(url_for('knowledge_base.detail', article_id=article_id))

            article_data = {
                'id': article_id,
                'title': title,
                'category': category,
                'tags': tags,
                'content': content,
                'status': status
            }
            return render_template(
                'knowledge_base/form.html',
                article=article_data,
                categories=categories,
                is_edit=True,
                active_page='knowledge_base'
            )

        return render_template(
            'knowledge_base/form.html',
            article=article,
            categories=categories,
            is_edit=True,
            active_page='knowledge_base'
        )
    finally:
        cur.close()
        conn.close()


@knowledge_base_bp.route('/<int:article_id>/delete', methods=['POST'])
@login_required
@roles_required('admin', 'it')
def delete(article_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM kb_articles WHERE id = %s;", (article_id,))
        article = cur.fetchone()
        if not article:
            abort(404)

        cur.execute("DELETE FROM kb_articles WHERE id = %s;", (article_id,))
        conn.commit()
        flash("Artikel berhasil dihapus!", "success")
        return redirect(url_for('knowledge_base.index'))
    finally:
        cur.close()
        conn.close()
