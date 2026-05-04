# Arito

Python/Pygame εφαρμογη μουσικης συνθεσης για αρχαριους.

## Features

- Menu με πολλαπλα instrument slots
- Instrument picker με GeneralUser-GS soundfont presets
- Piano Roll για melodic patterns
- Drum Rack για drum patterns
- Effects ανα slot
- Global project play bar στο Menu
- Save/Load project σε JSON

## Requirements

- Python 3.13
- pygame
- pyfluidsynth
- FluidSynth runtime
- GeneralUser-GS.sf2 soundfont

## Setup

```powershell
python -m pip install -r requirements.txt
```

Η εφαρμογη αυτη τη στιγμη φορτωνει soundfont απο:

```text
C:\tools\GeneralUser-GS.sf2
```

Αν το soundfont ειναι αλλου, αλλαξε το path στο `src/app.py`.

## Run

```powershell
python src/app.py
```

## Project Files

Τα saves γραφονται προεπιλεγμενα στο:

```text
Documents\Arito\Projects\last_project.json
```

## Notes

Μην ανεβαζεις `venv`, `__pycache__`, generated zips, ή local save files στο GitHub.
