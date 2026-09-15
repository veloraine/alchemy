# Reference Combiner

A tiny offline desktop utility for combining multiple reference images into a single image for Clip Studio Paint.

## Features

- Import PNG, JPG/JPEG, WEBP, and BMP images
- Drag-and-drop file import (Windows Explorer drag/drop via `windnd`) + Add Images button
- Thumbnail list with drag reordering, Move Left / Move Right, Delete, and Clear
- Layout presets: Horizontal, Vertical, 2x2, 3x1, 1x3, Auto/Masonry, and Custom columns
- Fit modes per image: Fit, Fill, Original size (aspect ratio preserved)
- Canvas controls: background color, gap, and outer margin
- Live preview updates on every change
- Export PNG (recommended default filename) and JPG (quality control)
- Output width options: Auto, 1920, 2560, 3840, Custom width
- Paste from clipboard (`Ctrl+V`) and copy combined image to clipboard (Windows)
- Double-click thumbnail to replace image
- Last-used settings are remembered locally

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Tests

```bash
python -m unittest discover -s tests
```

## Windows packaging (simple)

Use PyInstaller for a single-file executable:

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name ReferenceCombiner main.py
```

The executable will be created under `dist/ReferenceCombiner.exe`.

## Easier Windows launch

After installing dependencies once, you can launch with:

- Double-click `/home/runner/work/alchemy/alchemy/launch_reference_combiner.bat`
