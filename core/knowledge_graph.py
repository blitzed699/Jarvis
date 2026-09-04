"""
core/knowledge_graph.py

Knowledge Graph — Tier 2 Intelligence Amplification.
JARVIS builds a structured graph of everything it knows about:
  - Projects, people, APIs, tools, concepts, goals
  - Relationships between them

Entity types:
  person, project, tool, api, concept, goal, document, decision, event

Relation types:
  uses, depends_on, created_by, part_of, related_to, triggers,
  requires, contradicts, supersedes, authored_by, mentions
"""

import json
import sqlite3
import hashlib
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class Entity:
    id: str
    name: str
    entity_type: str
    properties: Dict[str, Any]
    created_at: str
    source: str = "manual"
    confidence: float = 1.0

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "type": self.entity_type,
            "properties": self.properties,
            "created_at": self.created_at,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass
class Relation:
    id: str
    from_id: str
    relation_type: str
    to_id: str
    properties: Dict[str, Any]
    created_at: str
    source: str = "manual"
    confidence: float = 1.0

    def to_dict(self):
        return {
            "id": self.id,
            "from": self.from_id,
            "relation": self.relation_type,
            "to": self.to_id,
            "properties": self.properties,
            "created_at": self.created_at,
            "source": self.source,
            "confidence": self.confidence,
        }


class KnowledgeGraph:
    VALID_ENTITY_TYPES = {
        "person", "project", "tool", "api", "concept",
        "goal", "document", "decision", "event", "organization", "product"
    }

    VALID_RELATION_TYPES = {
        "uses", "depends_on", "created_by", "part_of", "related_to",
        "triggers", "requires", "contradicts", "supersedes", "authored_by",
        "mentions", "owns", "manages", "leads_to", "blocks", "enables"
    }

    def __init__(self, db_path: str = "memory/knowledge_graph.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    properties TEXT DEFAULT '{}',
                    created_at TEXT,
                    source TEXT DEFAULT 'manual',
                    confidence REAL DEFAULT 1.0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS relations (
                    id TEXT PRIMARY KEY,
                    from_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    to_id TEXT NOT NULL,
                    properties TEXT DEFAULT '{}',
                    created_at TEXT,
                    source TEXT DEFAULT 'manual',
                    confidence REAL DEFAULT 1.0,
                    FOREIGN KEY (from_id) REFERENCES entities(id),
                    FOREIGN KEY (to_id) REFERENCES entities(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(entity_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_relation_from ON relations(from_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_relation_to ON relations(to_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_relation_type ON relations(relation_type)")
            conn.commit()

    def _db_conn(self):
        return sqlite3.connect(self.db_path)

    def _entity_id(self, name: str, entity_type: str) -> str:
        return f"ent_{hashlib.md5(f'{entity_type}:{name}'.encode()).hexdigest()[:12]}"

    def _relation_id(self, from_id: str, relation: str, to_id: str) -> str:
        return f"rel_{hashlib.md5(f'{from_id}:{relation}:{to_id}'.encode()).hexdigest()[:12]}"

    def add_entity(self, name: str, entity_type: str,
                   properties: Dict[str, Any] = None,
                   source: str = "manual", confidence: float = 1.0) -> Entity:
        if entity_type not in self.VALID_ENTITY_TYPES:
            entity_type = "concept"

        eid = self._entity_id(name, entity_type)
        now = datetime.now().isoformat()
        props = json.dumps(properties or {})

        with self._db_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO entities
                (id, name, entity_type, properties, created_at, source, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (eid, name, entity_type, props, now, source, confidence))
            conn.commit()

        return Entity(eid, name, entity_type, properties or {}, now, source, confidence)

    def get_entity(self, name: str, entity_type: str = None) -> Optional[Entity]:
        with self._db_conn() as conn:
            if entity_type:
                row = conn.execute(
                    "SELECT * FROM entities WHERE name = ? AND entity_type = ?",
                    (name, entity_type)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM entities WHERE name = ?",
                    (name,)
                ).fetchone()

            if row:
                return Entity(
                    id=row[0], name=row[1], entity_type=row[2],
                    properties=json.loads(row[3]), created_at=row[4],
                    source=row[5], confidence=row[6]
                )
            return None

    def get_entity_by_id(self, eid: str) -> Optional[Entity]:
        with self._db_conn() as conn:
            row = conn.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()
            if row:
                return Entity(
                    id=row[0], name=row[1], entity_type=row[2],
                    properties=json.loads(row[3]), created_at=row[4],
                    source=row[5], confidence=row[6]
                )
            return None

    def add_relation(self, from_name: str, relation_type: str, to_name: str,
                     from_type: str = None, to_type: str = None,
                     properties: Dict[str, Any] = None,
                     source: str = "manual", confidence: float = 1.0) -> Optional[Relation]:
        if relation_type not in self.VALID_RELATION_TYPES:
            relation_type = "related_to"

        from_entity = self.get_entity(from_name, from_type)
        to_entity = self.get_entity(to_name, to_type)

        if not from_entity:
            from_entity = self.add_entity(from_name, from_type or "concept")
        if not to_entity:
            to_entity = self.add_entity(to_name, to_type or "concept")

        rid = self._relation_id(from_entity.id, relation_type, to_entity.id)
        now = datetime.now().isoformat()
        props = json.dumps(properties or {})

        with self._db_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO relations
                (id, from_id, relation_type, to_id, properties, created_at, source, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (rid, from_entity.id, relation_type, to_entity.id, props, now, source, confidence))
            conn.commit()

        return Relation(rid, from_entity.id, relation_type, to_entity.id,
                        properties or {}, now, source, confidence)

    def query(self, entity_name: str = None, entity_type: str = None,
              relation: str = None, related_to: str = None,
              limit: int = 50) -> Dict[str, Any]:
        results = {"entities": [], "relations": []}

        with self._db_conn() as conn:
            if entity_name or entity_type:
                q = "SELECT * FROM entities WHERE 1=1"
                params = []
                if entity_name:
                    q += " AND name LIKE ?"
                    params.append(f"%{entity_name}%")
                if entity_type:
                    q += " AND entity_type = ?"
                    params.append(entity_type)
                q += f" LIMIT {limit}"
                rows = conn.execute(q, params).fetchall()
                results["entities"] = [
                    Entity(r[0], r[1], r[2], json.loads(r[3]), r[4], r[5], r[6]).to_dict()
                    for r in rows
                ]

            if relation or related_to or entity_name:
                q = """
                    SELECT r.*, e1.name as from_name, e2.name as to_name
                    FROM relations r
                    JOIN entities e1 ON r.from_id = e1.id
                    JOIN entities e2 ON r.to_id = e2.id
                    WHERE 1=1
                """
                params = []
                if relation:
                    q += " AND r.relation_type = ?"
                    params.append(relation)
                if related_to:
                    q += " AND (e1.name LIKE ? OR e2.name LIKE ?)"
                    params.extend([f"%{related_to}%", f"%{related_to}%"])
                if entity_name:
                    q += " AND (e1.name LIKE ? OR e2.name LIKE ?)"
                    params.extend([f"%{entity_name}%", f"%{entity_name}%"])
                q += f" LIMIT {limit}"
                rows = conn.execute(q, params).fetchall()
                results["relations"] = [
                    {
                        "id": r[0], "from_id": r[1], "relation": r[2], "to_id": r[3],
                        "properties": json.loads(r[4]), "created_at": r[5],
                        "source": r[6], "confidence": r[7],
                        "from_name": r[8], "to_name": r[9]
                    }
                    for r in rows
                ]

        return results

    def get_related(self, entity_name: str, relation: str = None,
                    direction: str = "both", depth: int = 1) -> List[Dict[str, Any]]:
        entity = self.get_entity(entity_name)
        if not entity:
            return []

        visited = {entity.id}
        frontier = {entity.id}
        all_results = []

        for d in range(depth):
            new_frontier = set()
            with self._db_conn() as conn:
                for eid in frontier:
                    if direction in ("outgoing", "both"):
                        rows = conn.execute("""
                            SELECT r.*, e.name as to_name, e.entity_type as to_type
                            FROM relations r
                            JOIN entities e ON r.to_id = e.id
                            WHERE r.from_id = ?
                        """ + (" AND r.relation_type = ?" if relation else ""),
                        (eid, relation) if relation else (eid,)).fetchall()
                        for r in rows:
                            if r[3] not in visited:
                                new_frontier.add(r[3])
                                all_results.append({
                                    "entity_id": r[3], "entity_name": r[8],
                                    "entity_type": r[9], "relation": r[2],
                                    "direction": "outgoing", "depth": d + 1,
                                    "confidence": r[7]
                                })

                    if direction in ("incoming", "both"):
                        rows = conn.execute("""
                            SELECT r.*, e.name as from_name, e.entity_type as from_type
                            FROM relations r
                            JOIN entities e ON r.from_id = e.id
                            WHERE r.to_id = ?
                        """ + (" AND r.relation_type = ?" if relation else ""),
                        (eid, relation) if relation else (eid,)).fetchall()
                        for r in rows:
                            if r[1] not in visited:
                                new_frontier.add(r[1])
                                all_results.append({
                                    "entity_id": r[1], "entity_name": r[8],
                                    "entity_type": r[9], "relation": r[2],
                                    "direction": "incoming", "depth": d + 1,
                                    "confidence": r[7]
                                })

            visited.update(new_frontier)
            frontier = new_frontier
            if not frontier:
                break

        return all_results

    def get_path(self, from_name: str, to_name: str,
                 max_depth: int = 5) -> Optional[List[Dict]]:
        from_e = self.get_entity(from_name)
        to_e = self.get_entity(to_name)
        if not from_e or not to_e:
            return None

        queue = [(from_e.id, [])]
        visited = {from_e.id}

        with self._db_conn() as conn:
            while queue:
                current_id, path = queue.pop(0)
                if current_id == to_e.id:
                    return path

                if len(path) >= max_depth:
                    continue

                rows = conn.execute("""
                    SELECT r.relation_type, r.to_id, e.name, r.confidence
                    FROM relations r
                    JOIN entities e ON r.to_id = e.id
                    WHERE r.from_id = ?
                    UNION
                    SELECT r.relation_type, r.from_id, e.name, r.confidence
                    FROM relations r
                    JOIN entities e ON r.from_id = e.id
                    WHERE r.to_id = ?
                """, (current_id, current_id)).fetchall()

                for rel_type, next_id, name, conf in rows:
                    if next_id not in visited:
                        visited.add(next_id)
                        queue.append((next_id, path + [{
                            "relation": rel_type,
                            "to_id": next_id,
                            "to_name": name,
                            "confidence": conf
                        }]))

        return None

    def extract_from_text(self, text: str, llm_client) -> Dict[str, Any]:
        if not llm_client:
            return {"entities_added": 0, "relations_added": 0}

        prompt = f"""Extract entities and relations from the following text.

Text:
{text[:2000]}

Return ONLY a JSON object with this exact structure:
{{
  "entities": [
    {{"name": "Entity Name", "type": "project|tool|api|person|concept|goal|decision", "properties": {{}}}}
  ],
  "relations": [
    {{"from": "Entity Name", "relation": "uses|depends_on|created_by|part_of|related_to|requires", "to": "Other Name", "properties": {{}}}}
  ]
}}

Use ONLY these relation types: uses, depends_on, created_by, part_of, related_to, requires.
Use ONLY these entity types: project, tool, api, person, concept, goal, decision, document.
Return ONLY the JSON. No markdown, no explanation."""

        try:
            raw = llm_client.generate(prompt, max_tokens=1000, temperature=0.2)
            import re
            raw = re.sub(r'```(?:json)?\s*', '', raw)
            raw = raw.replace('```', '')
            start = raw.find('{')
            end = raw.rfind('}')
            if start != -1 and end != -1:
                data = json.loads(raw[start:end+1])
                entities_added = 0
                relations_added = 0

                for e in data.get("entities", []):
                    self.add_entity(
                        e.get("name", ""),
                        e.get("type", "concept"),
                        e.get("properties", {}),
                        source="extraction",
                        confidence=0.7
                    )
                    entities_added += 1

                for r in data.get("relations", []):
                    self.add_relation(
                        r.get("from", ""),
                        r.get("relation", "related_to"),
                        r.get("to", ""),
                        properties=r.get("properties", {}),
                        source="extraction",
                        confidence=0.6
                    )
                    relations_added += 1

                return {"entities_added": entities_added, "relations_added": relations_added}
        except Exception as e:
            return {"entities_added": 0, "relations_added": 0, "error": str(e)}

    def summarize_entity(self, name: str) -> str:
        entity = self.get_entity(name)
        if not entity:
            return f"No knowledge about '{name}'."

        lines = [f"## {entity.name} ({entity.entity_type})"]
        if entity.properties:
            for k, v in entity.properties.items():
                lines.append(f"- {k}: {v}")

        outgoing = self.get_related(name, direction="outgoing", depth=1)
        incoming = self.get_related(name, direction="incoming", depth=1)

        if outgoing:
            lines.append("\n### Uses / Relates to:")
            for r in outgoing:
                lines.append(f"- {r['relation']} → {r['entity_name']} ({r['entity_type']})")

        if incoming:
            lines.append("\n### Used by / Related from:")
            for r in incoming:
                lines.append(f"- {r['relation']} ← {r['entity_name']} ({r['entity_type']})")

        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        with self._db_conn() as conn:
            entity_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            relation_count = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
            type_counts = conn.execute(
                "SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type"
            ).fetchall()
            rel_counts = conn.execute(
                "SELECT relation_type, COUNT(*) FROM relations GROUP BY relation_type"
            ).fetchall()

        return {
            "entities": entity_count,
            "relations": relation_count,
            "entity_types": {t: c for t, c in type_counts},
            "relation_types": {t: c for t, c in rel_counts},
        }
