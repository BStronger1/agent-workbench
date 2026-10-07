"""Durable provider journal: ambiguous in-flight calls are never replayed."""
import json, sqlite3, time
from pathlib import Path
class BudgetExceeded(Exception): pass
class AmbiguousCall(Exception): pass
class Journal:
    def __init__(self, path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS durations (run TEXT PRIMARY KEY, total INTEGER)')
            c.execute('CREATE TABLE IF NOT EXISTS calls (run TEXT, call TEXT, state TEXT, payload TEXT, PRIMARY KEY(run,call))')
    def connect(self):
        return sqlite3.connect(self.path, timeout=30)
    def rows(self, run):
        with self.connect() as c:
            return c.execute('SELECT call,state,payload FROM calls WHERE run=? ORDER BY rowid',(run,)).fetchall()
    def usage(self, run):
        rows=self.rows(run)
        replies=[json.loads(r[2]) for r in rows if r[1]=='complete']
        return {'inputTokens':sum(r['inputTokens'] for r in replies),
                'outputTokens':sum(r['outputTokens'] for r in replies),
                'usageKnown':all(r[1]=='complete' for r in rows) and all(r['usageKnown'] for r in replies),
                'calls':len(rows), 'roles':[r[0] for r in rows]}
    def add_duration(self, run, duration):
        with self.connect() as c:
            c.execute('INSERT INTO durations VALUES (?,?) ON CONFLICT(run) DO UPDATE SET total=total+excluded.total',(run,duration))
            return c.execute('SELECT total FROM durations WHERE run=?',(run,)).fetchone()[0]
    def invoke(self, run, call, budget, bound, fn):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT state,payload FROM calls WHERE run=? AND call=?',(run,call)).fetchone()
            if row:
                if row[0]=='complete': return json.loads(row[1])
                raise AmbiguousCall('Previous provider request has uncertain outcome; no automatic paid replay.')
            usage=self.usage(run)
            if not usage['usageKnown'] or usage['inputTokens']+usage['outputTokens']+bound>budget:
                raise BudgetExceeded('Conservative token budget stopped the next model call.')
            c.execute('INSERT INTO calls VALUES (?,?,?,?)',(run,call,'pending',''))
        started=time.monotonic()
        try: result=fn()
        except Exception as error:
            diagnostic={'errorType':type(error).__name__,'httpStatus':getattr(error,'status_code',None)}
            with self.connect() as c:
                c.execute('UPDATE calls SET payload=? WHERE run=? AND call=?',(json.dumps(diagnostic),run,call))
            raise
        result['durationMs']=round((time.monotonic()-started)*1000)
        with self.connect() as c:
            c.execute("UPDATE calls SET state='complete',payload=? WHERE run=? AND call=?",(json.dumps(result,ensure_ascii=False),run,call))
        return result