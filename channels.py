# settings/channels.py

# Slot 1..12 -> MIDI channels.
# Channel 9 is reserved for drums, so melodic slots skip it.
SLOT_CHANNELS = {
    1: 0,
    2: 1,
    3: 2,
    4: 3,
    5: 4,
    6: 5,
    7: 6,
    8: 7,
    9: 8,
    10: 10,
    11: 11,
    12: 12,
}

# Drums παραμένουν στο 9 (channel 10 σε 1-based)
DRUM_CHANNEL = 9
