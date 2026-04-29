import sys
import os
from pathlib import Path

TOOLS_MD = Path(r"C:\AI\nanobot-omega\workspace\TOOLS.md")
SKILLS_DIR = Path(r"C:\AI\nanobot-omega\workspace\skills")

def register_tool(name, description, code):
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = SKILLS_DIR / f"{name}.py"
    
    # Écriture du script
    file_path.write_text(code, encoding="utf-8")
    
    # Mise à jour du TOOLS.md
    content = TOOLS_MD.read_text(encoding="utf-8")
    new_entry = f"\n- **{name}** : {description} (Action: `python {file_path}`)"
    if new_entry not in content:
        TOOLS_MD.write_text(content + new_entry, encoding="utf-8")
    
    return f"Outil '{name}' enregistré et intégré à la conscience collective Omega."

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python OMEGA_FORGE.py <name> <description> <path_to_code>")
        sys.exit(1)
    
    name, desc, code_path = sys.argv[1:4]
    code = Path(code_path).read_text(encoding="utf-8")
    print(register_tool(name, desc, code))
