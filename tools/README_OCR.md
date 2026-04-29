# OCR local pour Nanobot / Gemini

Ce dossier contient un outil OCR local pour lire du texte dans :

- des captures d'écran PNG/JPG
- une zone précise de l'écran
- des screenshots générés par Playwright

## Fichier principal

- `C:\AI\nanobot-omega\tools\ocr_tool.py`

## Dépendances utilisées

- `easyocr`
- `Pillow`
- `mss`
- `pytesseract` si `tesseract.exe` est installé

Le script choisit automatiquement :

1. `tesseract` si `tesseract.exe` existe sur le PC
2. sinon `easyocr`

## Exemples

### OCR sur une image

```powershell
python "C:\AI\nanobot-omega\tools\ocr_tool.py" image "C:\AI\nanobot-omega\ocr_test_sample.png" --pretty
```

### Vérifier qu'un texte précis est présent

```powershell
python "C:\AI\nanobot-omega\tools\ocr_tool.py" image "C:\temp\capture.png" --contains "ceci est un test" --pretty
```

Code de sortie :

- `0` : succès
- `4` : OCR réussi mais le texte demandé n'a pas été trouvé
- `1` : erreur de traitement

### OCR sur tout l'écran

```powershell
python "C:\AI\nanobot-omega\tools\ocr_tool.py" screen --pretty
```

### OCR sur une région précise

```powershell
python "C:\AI\nanobot-omega\tools\ocr_tool.py" screen --x 100 --y 200 --width 700 --height 280 --capture-out "C:\temp\region.png" --pretty
```

### Sauvegarder l'image prétraitée

```powershell
python "C:\AI\nanobot-omega\tools\ocr_tool.py" image "C:\temp\capture.png" --save-preprocessed "C:\temp\capture_preprocessed.png" --pretty
```

## Sortie JSON

Le script renvoie :

- `text` : texte brut concaténé
- `items` : lignes / blocs reconnus
- `box` : position du texte
- `confidence` : score de confiance
- `metadata` : infos image / capture

## Intégration recommandée

### Avec Playwright

1. Faire le screenshot :

```python
await page.screenshot(path=r"C:\temp\page.png")
```

2. Lancer l'OCR :

```powershell
python "C:\AI\nanobot-omega\tools\ocr_tool.py" image "C:\temp\page.png" --contains "notion" --pretty
```

### Avec une validation d'interface

Exemples de contrôles :

- vérifier qu'un message de confirmation existe
- lire un code affiché
- confirmer qu'un bouton ou un titre est visible

## Remarques performance

- le premier appel `easyocr` est le plus lent, car le modèle se charge en mémoire
- les appels suivants sont généralement plus rapides
- pour les besoins très fréquents, garder un processus Python vivant réutilisant `ocr_tool.perform_ocr(...)`
