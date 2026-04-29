import os
import sqlite3
import hashlib
import time
from pathlib import Path
import logging

# Configuration
DB_PATH = r"C:\AI\nanobot-omega\workspace\memory\omega_knowledge.db"
PATHS_TO_INDEX = [
    r"C:\AI\nanobot-omega\workspace",
    r"C:\Users\user\Desktop",
    r"C:\Users\user\Documents"
]
EXTENSIONS = {'.txt', '.md', '.py', '.json', '.pdf', '.csv', '.log'}

logging.basicConfig(level=logging.INFO, format='[INDEXER] %(message)s')

def get_file_hash(path):
    try:
        return hashlib.md5(Path(path).read_bytes()).hexdigest()
    except:
        return None

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS files 
                 (path TEXT PRIMARY KEY, hash TEXT, last_indexed REAL, content TEXT)''')
    conn.commit()
    return conn

def index_files():
    conn = init_db()
    c = conn.cursor()
    
    for root_path in PATHS_TO_INDEX:
        if not os.path.exists(root_path): continue
        logging.info(f"Scanning {root_path}...")
        
        for root, dirs, files in os.walk(root_path):
            if '.git' in root or '__pycache__' in root or '.nanochrome_profile' in root: continue
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in EXTENSIONS:
                    full_path = os.path.join(root, file)
                    mtime = os.path.getmtime(full_path)
                    
                    # Check if already indexed and not modified
                    c.execute("SELECT hash FROM files WHERE path=?", (full_path,))
                    row = c.fetchone()
                    
                    if not row:
                        logging.info(f"Indexing new file: {file}")
                        try:
                            content = Path(full_path).read_text(encoding='utf-8', errors='ignore')
                            c.execute("INSERT INTO files VALUES (?, ?, ?, ?)", 
                                      (full_path, get_file_hash(full_path), time.time(), content))
                        except Exception as e:
                            logging.warning(f"Could not read {file}: {e}")
                    
    conn.commit()
    conn.close()

def query_memory(query):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Recherche par mot clé simple dans le contenu
    search = f"%{query}%"
    c.execute("SELECT path, content FROM files WHERE content LIKE ? OR path LIKE ? LIMIT 10", (search, search))
    results = c.fetchall()
    conn.close()
    return results

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        q = " ".join(sys.argv[2:])
        res = query_memory(q)
        for r in res:
            print(f"--- MATCH: {r[0]} ---")
            # Print a snippet
            snippet = r[1][:500].replace('\n', ' ')
            print(f"{snippet}...\n")
    else:
        index_files()
