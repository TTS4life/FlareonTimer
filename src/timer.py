from src.constants import BUFFER_MS, MS_TO_NS

def calculate_first_offset_beep(offset, interval, number_beeps):
    return offset - interval * (number_beeps - 1)

def get_offset_boundary(offsets_beeps, offset, interval, number_beeps):
    return offsets_beeps[0][0] if offsets_beeps else calculate_first_offset_beep(offset, interval, number_beeps)

def is_safe(elapsed, offset_boundary):
    return elapsed < (offset_boundary - BUFFER_MS) * MS_TO_NS

def shift(offsets, delta):
    return (offsets[0] + delta, offsets[1] + delta)

def shift_all(offsets, delta):
    return [shift(offset, delta) for offset in offsets]
