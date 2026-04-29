import sys
import os
import json
import asyncio
import subprocess
import logging
from pathlib import Path

# Config
OMEGA_ROOT = Path(r"C:\AI\nanobot-omega")
ORCHESTRATOR_SCRIPT = OMEGA_ROOT / "gemini_cli_orchestrator.py"

logging.basicConfig(level=logging.INFO, format='[HIVE] %(message)s')

async def run_subtask(prompt, task_id):
    logging.info(f"Démarrage Sous-Tâche {task_id}: {prompt[:50]}...")
    # Appelle l'orchestrateur existant pour utiliser un agent du pool
    cmd = [sys.executable, str(ORCHESTRATOR_SCRIPT), "run", prompt]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    return stdout.decode(encoding='utf-8', errors='ignore')

async def coordinate(master_prompt):
    logging.info(f"=== OMEGA HIVE COORDINATION START ===")
    
    # Étape 1 : Planification (On demande à un agent de découper le travail)
    planning_prompt = f"""Tu es l'Architecte de la Ruche Omega. 
    Décompose la demande suivante en maximum 3 sous-tâches indépendantes et parallèles.
    Réponds UNIQUEMENT sous forme de JSON : ["tâche 1", "tâche 2", "tâche 3"]
    Demande : {master_prompt}"""
    
    logging.info("Phase de Planification...")
    plan_raw = await run_subtask(planning_prompt, "PLANNER")
    
    try:
        # Nettoyage sommaire du JSON dans la réponse
        plan_json = plan_raw.split('[')[-1].split(']')[0]
        tasks = json.loads('[' + plan_json + ']')
    except:
        logging.warning("Échec de la planification structurée, exécution séquentielle simple.")
        tasks = [master_prompt]

    # Étape 2 : Exécution Parallèle
    logging.info(f"Lancement de {len(tasks)} agents en parallèle...")
    jobs = [run_subtask(t, i) for i, t in enumerate(tasks)]
    results = await asyncio.gather(*jobs)
    
    # Étape 3 : Synthèse
    logging.info("Phase de Synthèse finale...")
    final_prompt = f"Voici les résultats de mes agents pour la mission : {master_prompt}.\nSynthétise tout cela de manière concise :\n" + "\n---\n".join(results)
    final_report = await run_subtask(final_prompt, "SYNTHESIZER")
    
    print("\n" + "="*50)
    print("RAPPORT FINAL OMEGA HIVE")
    print("="*50)
    print(final_report)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python OMEGA_HIVE.py \"votre mission complexe\"")
        sys.exit(1)
    
    asyncio.run(coordinate(" ".join(sys.argv[1:])))
