# settings/drum_kits.py
# Ορισμοί Drum Kits + σταθερές για Drum Rack

# MIDI κανάλι 10 (0-based index = 9)
DRUM_CHANNEL = 9

# Προεπιλογή βημάτων (στήλες) στο pattern
DEFAULT_STEPS = 16

# Drum kits:
# Κάθε σετ έχει bank=128 (drums), program=0/1/2... και rows: λίστα (midi_note, label)
DRUM_KITS = {
    "Αφρική": {
        "bank": 128, "program": 0,
        "rows": [
            (36, "Kick"),
            (38, "Snare"),
            (42, "Hi-Hat Κλειστό"),
            (46, "Hi-Hat Ανοιχτό"),
            (60, "High Bongo"),
            (61, "Low Bongo"),
            (67, "Hi Agogo"),
            (68, "Low Agogo"),
            (70, "Maracas"),
        ],
    },
    "Χαρντ Ροκ": {
        "bank": 128, "program": 1,
        "rows": [
            (36, "Kick"),
            (38, "Snare"),
            (40, "Snare 2"),
            (41, "Low Floor Tom"),
            (45, "Low Tom"),
            (47, "Mid Tom"),
            (50, "High Tom"),
            (42, "HH Closed"),
            (46, "HH Open"),
            (49, "Crash"),
            (51, "Ride"),
        ],
    },
    "Τζαζ": {
        "bank": 128, "program": 2,
        "rows": [
            (36, "Kick (Feather)"),
            (38, "Snare"),
            (51, "Ride 1"),
            (59, "Ride 2 Bell"),
            (42, "HH Closed"),
            (46, "HH Open"),
            (57, "Crash 2"),
            (53, "Ride Bell"),
        ],
    },
}