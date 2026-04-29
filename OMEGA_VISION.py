import os
import sys
import json
from PIL import Image, ImageDraw, ImageFont

def apply_vision_grid(image_path, output_path, cell_size=100):
    """Dessine une grille de coordonnées sur le screenshot pour aider Gemini Vision à viser."""
    try:
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        width, height = img.size
        
        # Dessin de la grille
        for x in range(0, width, cell_size):
            draw.line([(x, 0), (x, height)], fill="red", width=1)
            draw.text((x+5, 5), str(x), fill="red")
            
        for y in range(0, height, cell_size):
            draw.line([(0, y), (width, y)], fill="red", width=1)
            draw.text((5, y+5), str(y), fill="red")
            
        img.save(output_path)
        return output_path
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python OMEGA_VISION.py <image_path>")
        sys.exit(1)
        
    path = sys.argv[1]
    out = path.replace(".jpg", "_grid.jpg").replace(".png", "_grid.png")
    print(f"Vision Grid générée : {apply_vision_grid(path, out)}")
