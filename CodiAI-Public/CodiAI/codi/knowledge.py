"""Chunked documents with optional real embeddings and lexical fallback."""
import json
import math
import re
import time
from .storage import new_id

def chunks(text, size=1200, overlap=150):
    for offset in range(0, len(text), size - overlap):
        part = text[offset:offset + size].strip()
        if part:
            yield part

def cosine(a, b):
    if len(a) != len(b):
        return -1
    denominator = math.sqrt(sum(x*x for x in a) * sum(y*y for y in b))
    return sum(x*y for x, y in zip(a, b)) / denominator if denominator else 0

class Knowledge:
    def __init__(self, store, llm):
        self.store, self.llm = store, llm

    def add(self, name, text, semantic=False):
        if not isinstance(name, str) or not 1 <= len(name) <= 240 or not isinstance(text, str) or not text.strip() or len(text) > 300000:
            raise ValueError("Нужен текстовый документ до 300 000 символов и название до 240 символов")
        parts = list(chunks(text))
        vectors, error = [None] * len(parts), None
        if semantic:
            try:
                for start in range(0, len(parts), 12):
                    batch = self.llm.embed(parts[start:start+12])
                    vectors[start:start+12] = batch
            except RuntimeError as exc:
                error = str(exc)
                vectors = [None] * len(parts)
        document = new_id()
        with self.store.db() as db:
            db.execute("INSERT INTO documents VALUES(?,?,?)", (document, name, time.time()))
            for position, (part, vector) in enumerate(zip(parts, vectors)):
                ident = new_id()
                db.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?)", (ident, document, position, part, json.dumps(vector) if vector else None, "embeddinggemma" if vector else None))
                db.execute("INSERT INTO chunk_search VALUES(?,?)", (ident, part))
        return {"id": document, "chunks": len(parts), "index": "semantic" if vectors[0] else "lexical", "warning": error}

    def list(self):
        with self.store.db() as db:
            return [dict(r) for r in db.execute("SELECT d.*,count(c.id) AS chunks,count(c.embedding) AS embedded FROM documents d LEFT JOIN chunks c ON c.document_id=d.id GROUP BY d.id ORDER BY d.created DESC")]

    def delete(self, ident):
        with self.store.db() as db:
            db.execute("DELETE FROM chunk_search WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=?)", (ident,))
            db.execute("DELETE FROM documents WHERE id=?", (ident,))

    def search(self, query, semantic=False, limit=4):
        vector = None
        tokens=[t for t in re.findall(r'[\w]+',query.lower())[:30] if t not in {'как','что','это','мне','про','для','или','это','расскажи','объясни','пожалуйста','такое','какие','напиши','сделай','можно','в','и','на','с','по'}]
        if not tokens:return []
        with self.store.db() as db:
            match=' OR '.join('"'+t+'"'+('*' if len(t)>=5 else '') for t in tokens)
            # Prefixes tolerate common Russian endings without a second model.
            stems=' OR '.join('"'+(t[:-2] if len(t)>6 and re.search('[а-я]',t) else t)+'"*' for t in tokens)
            lexical_rows=[]
            for expression in dict.fromkeys([match,stems]):
                if not expression:continue
                lexical_rows=[dict(r) for r in db.execute('SELECT c.id,c.document_id,c.position,c.content,d.name,bm25(chunk_search) AS score FROM chunk_search JOIN chunks c ON c.id=chunk_search.chunk_id JOIN documents d ON d.id=c.document_id WHERE chunk_search MATCH ? ORDER BY score LIMIT ?',(expression,limit))]
                if lexical_rows:return lexical_rows
        if semantic:
            with self.store.db() as db:
                has_vectors = db.execute("SELECT 1 FROM chunks WHERE embedding IS NOT NULL LIMIT 1").fetchone()
            if has_vectors:
                try:
                    vector = self.llm.embed([query[:4000]])[0]
                except RuntimeError:
                    pass
        with self.store.db() as db:
            semantic_rows=[]
            if vector:
                rows = [dict(r) for r in db.execute("SELECT c.*,d.name FROM chunks c JOIN documents d ON c.document_id=d.id WHERE embedding_model='embeddinggemma'")]
                for row in rows:
                    row["score"] = cosine(vector, json.loads(row["embedding"]))
                    row.pop("embedding")
                semantic_rows=sorted(rows, key=lambda r: r["score"], reverse=True)[:limit]
            return semantic_rows
