import sys
import pygame
from settings.config import WIDTH, HEIGHT, WINDOW_TITLE, FPS, BG_COLOR

from screens.menu import MenuScreen
from screens.instrument import InstrumentScreen
from screens.instrument_picker import InstrumentPicker
from screens.piano_roll import PianoRollScreen
from screens.effects import EffectsScreen
from screens.drum_rack import DrumRackScreen   # <-- ΝΕΟ

from tools.audio_engine import apply_slot_effects

from settings.selections import INSTRUMENT_DATA
from tools.audio_engine import init as audio_init
from tools import metronome as MET
from tools.project_store import save_project, load_project
from tools.project_transport import PROJECT_TRANSPORT, apply_all_slot_presets_effects, apply_slot_preset as transport_apply_slot_preset





def run():
    # Ήχος / pygame
    pygame.mixer.pre_init(frequency=44100, size=-16, channels=1, buffer=512)
    pygame.init()
    MET.init()

    audio_init("C:\\tools\\GeneralUser-GS.sf2")

    # === ΣΗΜΑΝΤΙΚΟ ===
    # ΜΗΝ περνάς custom path. Άστο να βρει μόνο του το embedded .sf2:
    # project/src/tools/soundfonts/GeneralUser-GS.sf2
    # audio_init()

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(WINDOW_TITLE)
    clock = pygame.time.Clock()

    current_screen = "menu"
    menu_screen = MenuScreen()
    instrument_screen = None
    instrument_picker_screen = None
    piano_roll_screen = None
    effects_screen = None
    drum_rack_screen = None

    running = True
    while running:
        # --- Events ---
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            # --- Global shortcuts: Save/Load project ---
            
            if event.type == pygame.KEYDOWN:
                mods = pygame.key.get_mods()
                ctrl = bool(mods & pygame.KMOD_CTRL)
                
                if ctrl and event.key == pygame.K_s:
                    try:
                        saved_path = save_project()
                        menu_screen.set_status(f"Saved: {saved_path.name}")
                        print("Project saved.")
                    except Exception as e:
                        menu_screen.set_status("Save failed")
                        print("Save failed:", e)
                    continue;

                if ctrl and event.key == pygame.K_o:
                    try:
                        loaded_path = load_project()
                        PROJECT_TRANSPORT.stop()
                        apply_all_slot_presets_effects()
                        menu_screen.on_project_loaded()
                        menu_screen.set_status(f"Loaded: {loaded_path.name}")
                        print("Project loaded.")
                        # (Προαιρετικό) γύρνα στο menu μετά το load
                        current_screen = "menu"
                    except Exception as e:
                        menu_screen.set_status("Load failed")
                        print("Load failed:", e)

            if current_screen == "menu":
                next_state = menu_screen.handle_event(event)
                if next_state == "save_project":
                    try:
                        saved_path = save_project()
                        menu_screen.set_status(f"Saved: {saved_path.name}")
                        print("Project saved.")
                    except Exception as e:
                        menu_screen.set_status("Save failed")
                        print("Save failed:", e)
                elif next_state == "load_project":
                    try:
                        loaded_path = load_project()
                        PROJECT_TRANSPORT.stop()
                        apply_all_slot_presets_effects()
                        menu_screen.on_project_loaded()
                        menu_screen.set_status(f"Loaded: {loaded_path.name}")
                        print("Project loaded.")
                        current_screen = "menu"
                    except Exception as e:
                        menu_screen.set_status("Load failed")
                        print("Load failed:", e)
                elif next_state and next_state.startswith("instrument"):
                    PROJECT_TRANSPORT.stop()
                    index = int(next_state.split()[-1])
                    instrument_screen = InstrumentScreen(index, data=INSTRUMENT_DATA)
                    current_screen = next_state

            elif current_screen.startswith("instrument_picker"):
                next_state = instrument_picker_screen.handle_event(event)
                if next_state and next_state.startswith("instrument"):
                    current_screen = next_state
                elif next_state and next_state.startswith("drum_rack"):
                    index = int(next_state.split()[-1])
                    apply_slot_effects(index)
                    drum_rack_screen = DrumRackScreen(index)
                    current_screen = next_state

            elif current_screen.startswith("piano_roll"):
                next_state = piano_roll_screen.handle_event(event)
                if next_state and next_state.startswith("instrument"):
                    current_screen = next_state

            elif current_screen.startswith("effects"):
                next_state = effects_screen.handle_event(event)
                if next_state and next_state.startswith("instrument"):
                    current_screen = next_state

            elif current_screen.startswith("drum_rack"):
                next_state = drum_rack_screen.handle_event(event)
                if next_state and next_state.startswith("instrument"):
                    current_screen = next_state

            else:
                # Instrument Hub
                next_state = instrument_screen.handle_event(event)
                if next_state and next_state.startswith("instrument_picker"):
                    index = int(next_state.split()[-1])
                    instrument_picker_screen = InstrumentPicker(index)
                    current_screen = next_state
                elif next_state and next_state.startswith("piano_roll"):
                    index = int(next_state.split()[-1])
                    transport_apply_slot_preset(index)
                    
                    # Αν έρχομαι από Drum Rack -> σβήσε και drum + piano patterns
                    if current_screen.startswith("drum_rack"):
                        clear_slot_patterns(index)

                    piano_roll_screen = PianoRollScreen(index)
                    current_screen = next_state
                elif next_state and next_state.startswith("effects"):
                    index = int(next_state.split()[-1])
                    effects_screen = EffectsScreen(index)
                    current_screen = next_state
                elif next_state and next_state.startswith("drum_rack"):
                    index = int(next_state.split()[-1])
                    transport_apply_slot_preset(index)

                    # Αν έρχομαι από Drum Rack -> σβήσε και drum + piano patterns
                    if current_screen.startswith("piano_roll"):
                        clear_slot_patterns(index)

                    drum_rack_screen = DrumRackScreen(index)
                    current_screen = next_state
                elif next_state == "menu":
                    current_screen = "menu"
                    instrument_screen = None

        PROJECT_TRANSPORT.update()

        # --- Draw ---
        screen.fill(BG_COLOR)
        if current_screen == "menu":
            menu_screen.draw(screen)
        elif current_screen.startswith("instrument_picker"):
            instrument_picker_screen.draw(screen)
        elif current_screen.startswith("piano_roll"):
            piano_roll_screen.draw(screen)
        elif current_screen.startswith("effects"):
            effects_screen.draw(screen)
        elif current_screen.startswith("drum_rack"):
            drum_rack_screen.draw(screen)
        else:
            instrument_screen.draw(screen)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()

def apply_slot_preset(index: int) -> None:
    """
    Εφαρμόζει το preset του slot από το INSTRUMENT_DATA.
    Έτσι, μετά από Load, ο ήχος είναι σωστός χωρίς να περάσεις ξανά από InstrumentPicker.
    """
    transport_apply_slot_preset(index)

def clear_slot_patterns(index: int) -> None:
    """
    Σβήνει ΟΛΑ τα patterns του slot (piano roll + drum rack).
    Έτσι όταν μηδέν.
    """
    slot = INSTRUMENT_DATA.setdefault(index, {})
    slot.pop("piano_roll", None)
    slot.pop("drum_rack", None)

if __name__ == "__main__":
    run()
