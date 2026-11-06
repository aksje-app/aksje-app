"""Send large restart documents as data, never as a giant SQL literal.

psycopg2 v2 substitutes text parameters into SQL. PostgreSQL's SQL parser can
then retain several copies of the entire document. Binary COPY into a temporary
row avoids that parser expansion; the final upsert stays in the caller's locked
transaction. No staging row survives commit/rollback or connection closure.
"""
import struct
import logging


class BinaryTextRow:
    """One ASCII JSON text field, streamed with bounded extra client memory."""
    def __init__(self, payload):
        if not payload.isascii():
            raise ValueError('Large JSON COPY requires ASCII JSON serialization')
        self.payload = payload
        self.prefix = b'PGCOPY\n\xff\r\n\x00' + struct.pack('!ii', 0, 0) + struct.pack('!hi', 1, len(payload))
        self.position = 0

    def read(self, size=65536):
        if size < 0:
            size = 65536
        start = self.position
        end = min(start + size, len(self.prefix) + len(self.payload) + 2)
        chunks = []
        prefix_end = min(end, len(self.prefix))
        if start < prefix_end:
            chunks.append(self.prefix[start:prefix_end])
        body_start = max(start, len(self.prefix)) - len(self.prefix)
        body_end = min(end - len(self.prefix), len(self.payload))
        if body_start < body_end:
            chunks.append(self.payload[body_start:body_end].encode('ascii'))
        trailer_start = max(start - len(self.prefix) - len(self.payload), 0)
        trailer_end = end - len(self.prefix) - len(self.payload)
        if trailer_end > trailer_start:
            chunks.append(b'\xff\xff'[trailer_start:trailer_end])
        self.position = end
        return b''.join(chunks)


def write_restart_payload(cur, name, payload, *, skip_unchanged=False):
    cur.execute('CREATE TEMP TABLE app_restart_payload (payload TEXT NOT NULL) ON COMMIT DROP')
    cur.copy_expert('COPY app_restart_payload (payload) FROM STDIN WITH (FORMAT binary)', BinaryTextRow(payload))
    query = '''INSERT INTO app_kv_store (name, payload, updated_at)
        SELECT %s, payload, NOW()::TEXT FROM app_restart_payload
        ON CONFLICT (name) DO UPDATE
        SET payload=EXCLUDED.payload, updated_at=EXCLUDED.updated_at'''
    if skip_unchanged:
        query += ' WHERE app_kv_store.payload IS DISTINCT FROM EXCLUDED.payload'
    cur.execute(query, (name,))
    logging.warning('LARGE_JSON_WRITE_STAGED key=%s transport=binary_copy bytes=%s', name, len(payload))
