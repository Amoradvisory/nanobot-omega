import json
from concurrent.futures import ThreadPoolExecutor
import os

def load_instances():
    file_path = r"C:\AI\nanobot-omega\instances_swarm.json"
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("instances", [])

def call_single_instance(inst, prompt):
    print(f"[SWARM] Instance {inst['id']} lancee en parallele")
    # Simulation de l'appel a GeminiInstance
    # Dans une version reelle, on importerait GeminiInstance ici
    return f"Reponse simulee {inst['id']} - a remplacer par l'appel reel GeminiInstance"

def gemini_swarm(prompt):
    instances = load_instances()
    if not instances:
        return "Erreur : aucune instance configuree dans instances_swarm.json"
        
    with ThreadPoolExecutor(max_workers=len(instances)) as executor:
        futures = [executor.submit(call_single_instance, inst, prompt) for inst in instances]
        results = [future.result() for future in futures]
    
    # Filtrage des reponses valides
    valid = [r for r in results if r and "erreur" not in r.lower()]
    
    if valid:
        # On pourrait ici agréger les réponses, mais selon le script initial :
        return valid[0] 
    elif results:
        return results[0]
    else:
        return "Aucune reponse valide"

if __name__ == "__main__":
    prompt = "Test de swarm"
    print(f"\nResultat du Swarm :\n{gemini_swarm(prompt)}")