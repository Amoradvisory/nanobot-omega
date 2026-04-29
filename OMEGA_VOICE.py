import sys
import subprocess

def speak(text):
    # Échappe les guillemets simples pour PowerShell
    safe_text = text.replace("'", "''")
    ps_cmd = f"Add-Type -AssemblyName System.Speech; $speak = New-Object System.Speech.Synthesis.SpeechSynthesizer; $speak.Speak('{safe_text}')"
    
    subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python OMEGA_VOICE.py \"votre texte\"")
        sys.exit(1)
        
    msg = " ".join(sys.argv[1:])
    print(f"Omega parle : {msg}")
    speak(msg)
