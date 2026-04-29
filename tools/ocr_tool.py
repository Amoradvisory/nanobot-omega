from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

try:
    import easyocr
except ImportError:  # pragma: no cover - environment dependent
    easyocr = None

try:
    import pytesseract
    from pytesseract import Output as TesseractOutput
except ImportError:  # pragma: no cover - environment dependent
    pytesseract = None
    TesseractOutput = None

warnings.filterwarnings(
    "ignore",
    message=".*pin_memory.*no accelerator is found.*",
    category=UserWarning,
)


EngineName = Literal["auto", "windows", "easyocr", "tesseract"]


COMMON_TESSERACT_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


@dataclass(slots=True)
class OCRBox:
    left: int
    top: int
    width: int
    height: int


@dataclass(slots=True)
class OCRItem:
    text: str
    confidence: float
    box: OCRBox
    engine: str


@dataclass(slots=True)
class OCRResult:
    success: bool
    engine: str
    source: str
    text: str
    elapsed_ms: int
    items: list[OCRItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    contains: bool | None = None
    contains_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["items"] = [
            {
                "text": item.text,
                "confidence": item.confidence,
                "box": asdict(item.box),
                "engine": item.engine,
            }
            for item in self.items
        ]
        return payload


def _find_tesseract() -> str | None:
    resolved = shutil.which("tesseract")
    if resolved:
        return resolved
    for path in COMMON_TESSERACT_PATHS:
        if Path(path).exists():
            return path
    return None


def _ps_single(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _run_powershell_json(script: str, timeout: int = 60) -> dict[str, Any]:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(error or output or f"PowerShell exit {result.returncode}")
    if not output:
        return {}
    return json.loads(output)


def _windows_ocr(image_path: Path, languages: list[str]) -> tuple[list[OCRItem], dict[str, Any], list[str]]:
    script = rf"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }})[0]
function Await($operation, [type]$resultType) {{
  $asTask = $asTaskGeneric.MakeGenericMethod($resultType)
  $task = $asTask.Invoke($null, @($operation))
  $task.Wait()
  return $task.Result
}}
$imagePath = {_ps_single(image_path)}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($imagePath)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
try {{
  $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
  if ($null -eq $engine) {{ throw 'Windows OCR engine unavailable for current user languages.' }}
  $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
  $items = @()
  foreach ($line in $result.Lines) {{
    foreach ($word in $line.Words) {{
      $items += [PSCustomObject]@{{
        text = $word.Text
        confidence = 1.0
        box = [PSCustomObject]@{{
          left = [int]$word.BoundingRect.X
          top = [int]$word.BoundingRect.Y
          width = [int]$word.BoundingRect.Width
          height = [int]$word.BoundingRect.Height
        }}
        engine = 'windows'
      }}
    }}
  }}
  [PSCustomObject]@{{
    ok = $true
    text = (($result.Lines | ForEach-Object {{ $_.Text }}) -join "`n")
    image_width = [int]$bitmap.PixelWidth
    image_height = [int]$bitmap.PixelHeight
    items = $items
  }} | ConvertTo-Json -Depth 8 -Compress
}} finally {{
  if ($stream) {{ $stream.Dispose() }}
}}
"""
    payload = _run_powershell_json(script)
    raw_items = payload.get("items") or []
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    items: list[OCRItem] = []
    for raw in raw_items:
        box = raw.get("box") or {}
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        items.append(
            OCRItem(
                text=text,
                confidence=float(raw.get("confidence") or 1.0),
                box=OCRBox(
                    left=int(box.get("left") or 0),
                    top=int(box.get("top") or 0),
                    width=int(box.get("width") or 0),
                    height=int(box.get("height") or 0),
                ),
                engine="windows",
            )
        )
    metadata = {
        "image_width": int(payload.get("image_width") or 0),
        "image_height": int(payload.get("image_height") or 0),
        "languages": languages,
        "preprocess": False,
        "line_text": str(payload.get("text") or ""),
    }
    warnings_out = ["Windows OCR ignores requested language list and uses current user profile languages."]
    return items, metadata, warnings_out


def _capture_screen_region_windows(
    *,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    output_path: str | Path | None = None,
) -> Path:
    target = Path(output_path) if output_path is not None else Path.cwd() / f"ocr_capture_{int(time.time())}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    if None not in (x, y, width, height):
        region_block = f"""
$left = {int(x)}
$top = {int(y)}
$width = {int(width)}
$height = {int(height)}
"""
    else:
        region_block = """
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$left = $bounds.Left
$top = $bounds.Top
$width = $bounds.Width
$height = $bounds.Height
"""
    script = rf"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
{region_block}
$target = {_ps_single(target)}
$bmp = New-Object System.Drawing.Bitmap($width, $height)
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
try {{
  $graphics.CopyFromScreen($left, $top, 0, 0, $bmp.Size)
  $bmp.Save($target, [System.Drawing.Imaging.ImageFormat]::Png)
  [PSCustomObject]@{{ ok = $true; path = $target }} | ConvertTo-Json -Compress
}} finally {{
  $graphics.Dispose()
  $bmp.Dispose()
}}
"""
    payload = _run_powershell_json(script, timeout=30)
    return Path(payload.get("path") or target)


def _select_engine(engine: EngineName) -> str:
    if engine == "windows":
        if sys.platform != "win32":
            raise RuntimeError("Windows OCR is only available on Windows.")
        return "windows"
    if engine == "easyocr":
        if easyocr is None:
            raise RuntimeError("easyocr n'est pas installé.")
        return "easyocr"
    if engine == "tesseract":
        if pytesseract is None:
            raise RuntimeError("pytesseract n'est pas installé.")
        tesseract_path = _find_tesseract()
        if not tesseract_path:
            raise RuntimeError("tesseract.exe est introuvable sur ce PC.")
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        return "tesseract"

    if pytesseract is not None:
        tesseract_path = _find_tesseract()
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            return "tesseract"
    if easyocr is not None:
        return "easyocr"
    if sys.platform == "win32":
        return "windows"
    raise RuntimeError("Aucun moteur OCR disponible.")


def _normalize_languages(languages: list[str] | tuple[str, ...] | None) -> list[str]:
    if not languages:
        return ["fr", "en"]
    normalized = [lang.strip().lower() for lang in languages if lang and lang.strip()]
    return normalized or ["fr", "en"]


def _tesseract_language_code(languages: list[str]) -> str:
    mapping = {
        "fr": "fra",
        "fra": "fra",
        "en": "eng",
        "eng": "eng",
        "nl": "nld",
        "de": "deu",
        "es": "spa",
    }
    codes = [mapping.get(lang, lang) for lang in languages]
    deduped: list[str] = []
    for code in codes:
        if code not in deduped:
            deduped.append(code)
    return "+".join(deduped)


def _get_easyocr_reader(languages: list[str]):
    if easyocr is None:
        raise RuntimeError("easyocr n'est pas installé.")
    cache = getattr(_get_easyocr_reader, "_cache", {})
    key = tuple(languages)
    if key not in cache:
        cache[key] = easyocr.Reader(languages, gpu=False, verbose=False)
        setattr(_get_easyocr_reader, "_cache", cache)
    return cache[key]


def _preprocess_image(image: Image.Image) -> Image.Image:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps

    working = ImageOps.exif_transpose(image.convert("RGB"))
    grayscale = ImageOps.grayscale(working)
    grayscale = ImageOps.autocontrast(grayscale)

    min_side = min(grayscale.size)
    if min_side < 900:
        scale = max(2, int(900 / max(min_side, 1)))
        grayscale = grayscale.resize(
            (grayscale.width * scale, grayscale.height * scale),
            Image.Resampling.LANCZOS,
        )

    grayscale = ImageEnhance.Contrast(grayscale).enhance(1.5)
    grayscale = grayscale.filter(ImageFilter.SHARPEN)
    return grayscale


def capture_screen_region(
    *,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    output_path: str | Path | None = None,
) -> Path:
    try:
        from mss import mss
        from PIL import Image
    except ImportError:
        if sys.platform == "win32":
            return _capture_screen_region_windows(
                x=x,
                y=y,
                width=width,
                height=height,
                output_path=output_path,
            )
        raise

    with mss() as sct:
        if None not in (x, y, width, height):
            monitor = {"left": x, "top": y, "width": width, "height": height}
        else:
            monitor = dict(sct.monitors[1])

        shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.rgb)

        if output_path is None:
            target = Path.cwd() / f"ocr_capture_{int(time.time())}.png"
        else:
            target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target)
        return target


def _ocr_with_easyocr(image: Image.Image, languages: list[str]) -> list[OCRItem]:
    import numpy as np

    reader = _get_easyocr_reader(languages)
    raw_items = reader.readtext(np.array(image), detail=1, paragraph=False)
    items: list[OCRItem] = []
    for polygon, text, confidence in raw_items:
        if not text or not str(text).strip():
            continue
        xs = [int(point[0]) for point in polygon]
        ys = [int(point[1]) for point in polygon]
        left = min(xs)
        top = min(ys)
        right = max(xs)
        bottom = max(ys)
        items.append(
            OCRItem(
                text=str(text).strip(),
                confidence=float(confidence),
                box=OCRBox(
                    left=left,
                    top=top,
                    width=max(0, right - left),
                    height=max(0, bottom - top),
                ),
                engine="easyocr",
            )
        )
    return items


def _ocr_with_tesseract(image: Image.Image, languages: list[str]) -> list[OCRItem]:
    if pytesseract is None or TesseractOutput is None:
        raise RuntimeError("pytesseract n'est pas installé.")
    lang = _tesseract_language_code(languages)
    raw = pytesseract.image_to_data(image, lang=lang, output_type=TesseractOutput.DICT)
    items: list[OCRItem] = []
    total = len(raw["text"])
    for index in range(total):
        text = (raw["text"][index] or "").strip()
        if not text:
            continue
        confidence_raw = raw["conf"][index]
        try:
            confidence = max(0.0, min(1.0, float(confidence_raw) / 100.0))
        except (TypeError, ValueError):
            confidence = 0.0
        items.append(
            OCRItem(
                text=text,
                confidence=confidence,
                box=OCRBox(
                    left=int(raw["left"][index]),
                    top=int(raw["top"][index]),
                    width=int(raw["width"][index]),
                    height=int(raw["height"][index]),
                ),
                engine="tesseract",
            )
        )
    return items


def perform_ocr(
    image_path: str | Path,
    *,
    engine: EngineName = "auto",
    languages: list[str] | tuple[str, ...] | None = None,
    contains_text: str | None = None,
    preprocess: bool = True,
    save_preprocessed_path: str | Path | None = None,
) -> OCRResult:
    started = time.perf_counter()
    source_path = Path(image_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Image introuvable: {source_path}")

    selected_engine = _select_engine(engine)
    normalized_languages = _normalize_languages(languages)
    warnings: list[str] = []

    if selected_engine == "windows":
        items, metadata, engine_warnings = _windows_ocr(source_path, normalized_languages)
        warnings.extend(engine_warnings)
        if preprocess:
            warnings.append("Preprocessing is skipped by the native Windows OCR fallback.")
        if save_preprocessed_path is not None:
            warnings.append("save_preprocessed_path is ignored by the native Windows OCR fallback.")
        text = str(metadata.get("line_text") or "").strip() or "\n".join(item.text for item in items)
        if not items:
            warnings.append("Aucun texte dÃ©tectÃ©.")
        contains = None
        if contains_text is not None:
            contains = contains_text.casefold() in text.casefold()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return OCRResult(
            success=True,
            engine=selected_engine,
            source=str(source_path),
            text=text,
            elapsed_ms=elapsed_ms,
            items=items,
            warnings=warnings,
            metadata=metadata,
            contains=contains,
            contains_text=contains_text,
        )

    from PIL import Image, ImageOps

    with Image.open(source_path) as opened:
        original = ImageOps.exif_transpose(opened)
        working = _preprocess_image(original) if preprocess else original.convert("RGB")
        metadata = {
            "image_width": original.width,
            "image_height": original.height,
            "languages": normalized_languages,
            "preprocess": preprocess,
        }

        if save_preprocessed_path is not None:
            save_target = Path(save_preprocessed_path)
            save_target.parent.mkdir(parents=True, exist_ok=True)
            working.save(save_target)
            metadata["preprocessed_image"] = str(save_target)

        if selected_engine == "easyocr":
            items = _ocr_with_easyocr(working, normalized_languages)
        else:
            items = _ocr_with_tesseract(working, normalized_languages)

    text = "\n".join(item.text for item in items)
    if not items:
        warnings.append("Aucun texte détecté.")

    contains = None
    if contains_text is not None:
        contains = contains_text.casefold() in text.casefold()

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return OCRResult(
        success=True,
        engine=selected_engine,
        source=str(source_path),
        text=text,
        elapsed_ms=elapsed_ms,
        items=items,
        warnings=warnings,
        metadata=metadata,
        contains=contains,
        contains_text=contains_text,
    )


def perform_ocr_on_screen_region(
    *,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    capture_path: str | Path | None = None,
    engine: EngineName = "auto",
    languages: list[str] | tuple[str, ...] | None = None,
    contains_text: str | None = None,
    preprocess: bool = True,
) -> OCRResult:
    capture = capture_screen_region(
        x=x,
        y=y,
        width=width,
        height=height,
        output_path=capture_path,
    )
    result = perform_ocr(
        capture,
        engine=engine,
        languages=languages,
        contains_text=contains_text,
        preprocess=preprocess,
    )
    result.metadata["captured"] = True
    result.metadata["capture_path"] = str(capture)
    if None not in (x, y, width, height):
        result.metadata["region"] = {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        }
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OCR local pour Nanobot/Gemini sur images ou capture d'écran."
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--engine",
        choices=("auto", "windows", "easyocr", "tesseract"),
        default="auto",
        help="Moteur OCR à utiliser.",
    )
    common.add_argument(
        "--lang",
        nargs="+",
        default=["fr", "en"],
        help="Langues OCR (ex: fr en).",
    )
    common.add_argument(
        "--contains",
        help="Texte attendu à rechercher dans le résultat OCR.",
    )
    common.add_argument(
        "--no-preprocess",
        action="store_true",
        help="Désactive le prétraitement d'image.",
    )
    common.add_argument(
        "--pretty",
        action="store_true",
        help="Affiche le JSON de manière lisible.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    image_cmd = sub.add_parser(
        "image",
        parents=[common],
        help="OCR sur une image existante.",
    )
    image_cmd.add_argument("image_path", help="Chemin du fichier image.")
    image_cmd.add_argument(
        "--save-preprocessed",
        help="Chemin où sauvegarder l'image prétraitée.",
    )

    screen_cmd = sub.add_parser(
        "screen",
        parents=[common],
        help="OCR sur une capture d'écran.",
    )
    screen_cmd.add_argument("--x", type=int)
    screen_cmd.add_argument("--y", type=int)
    screen_cmd.add_argument("--width", type=int)
    screen_cmd.add_argument("--height", type=int)
    screen_cmd.add_argument(
        "--capture-out",
        help="Chemin du PNG de capture à enregistrer.",
    )

    return parser


def _result_to_json(result: OCRResult, *, pretty: bool) -> str:
    if pretty:
        return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    return json.dumps(result.to_dict(), ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "image":
            result = perform_ocr(
                args.image_path,
                engine=args.engine,
                languages=args.lang,
                contains_text=args.contains,
                preprocess=not args.no_preprocess,
                save_preprocessed_path=args.save_preprocessed,
            )
        else:
            if any(value is not None for value in (args.x, args.y, args.width, args.height)):
                if None in (args.x, args.y, args.width, args.height):
                    raise ValueError("Pour une région d'écran, x, y, width et height sont tous requis.")
            result = perform_ocr_on_screen_region(
                x=args.x,
                y=args.y,
                width=args.width,
                height=args.height,
                capture_path=args.capture_out,
                engine=args.engine,
                languages=args.lang,
                contains_text=args.contains,
                preprocess=not args.no_preprocess,
            )
    except Exception as exc:
        payload = {
            "success": False,
            "error": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    print(_result_to_json(result, pretty=args.pretty))
    if args.contains is not None and result.contains is False:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
