import os
import psutil
import time
import logging
import subprocess

# Config
CHROME_PROCESS_NAME = "chrome.exe"
CPU_THRESHOLD = 80.0  # %
MEM_THRESHOLD_GB = 4.0
MAX_LIFETIME_SEC = 3600 * 4 # Relance Chrome toutes les 4h pour éviter les fuites de RAM

logging.basicConfig(level=logging.INFO, format='[SENTINELLE] %(message)s')

def clean_zombie_processes():
    logging.info("Vérification des processus zombies...")
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'create_time']):
        try:
            # Nettoyage Chrome
            if proc.info['name'] == CHROME_PROCESS_NAME:
                mem_gb = proc.info['memory_info'].rss / (1024 ** 3)
                uptime = time.time() - proc.info['create_time']
                
                if mem_gb > MEM_THRESHOLD_GB or uptime > MAX_LIFETIME_SEC:
                    logging.warning(f"Kill processus Chrome {proc.info['pid']} (RAM: {mem_gb:.2f}GB, Uptime: {uptime/60:.1f}min)")
                    proc.kill()
            
            # Nettoyage Mutex orphelins (fichiers lock bloqués)
            # (Optionnel : On pourrait vérifier si un fichier .lock existe mais sans process associé)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

def check_internet():
    try:
        subprocess.check_call(["ping", "-n", "1", "8.8.8.8"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except:
        return False

def run_maintenance():
    logging.info("=== Cycle de Maintenance Omega ===")
    
    # 1. Nettoyage des processus
    clean_zombie_processes()
    
    # 2. Vérification Réseau
    if not check_internet():
        logging.error("Panne Internet détectée. Tentative de reset DNS...")
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
    
    # 3. Nettoyage logs anciens (> 7 jours)
    log_dir = r"C:\AI\nanobot-omega\logs"
    if os.path.exists(log_dir):
        now = time.time()
        for f in os.listdir(log_dir):
            fp = os.path.join(log_dir, f)
            if os.stat(fp).st_mtime < now - 7 * 86400:
                os.remove(fp)
                logging.info(f"Log ancien supprimé : {f}")

if __name__ == "__main__":
    while True:
        run_maintenance()
        logging.info("Système sain. Prochain scan dans 30 minutes.")
        time.sleep(1800)
