from dotenv import load_dotenv
import os
load_dotenv()
default_palette = 13 # REMINDER to change this
pxlslog_explorer_dir = os.getenv("pxlslog_explorer_dir")

def owner():
    """Defining an owner within Tib."""
    owner_id = os.getenv("owner_id")
    if owner_id is None:
        raise ValueError("owner_id not set!")
    return int(owner_id)
def update_channel():
    """Channel for Tib status updates (rankups, placemap stats, etc.)"""
    update_channel_id = os.getenv("update_channel_id")
    if update_channel_id is None:
        raise ValueError("update_channel_id not set!")
    return int(update_channel_id)

def get_palette(canvas: str):
    """A simple function to find the palette of a canvas. If it isn't found, apply a default palette."""
    match canvas:
        case "1"|"2":
            return 1
        case "3"|"4"|"5"|"6"|"7":
            return 2
        case "8"|"9"|"10"|"11":
            return 3
        case "12"|"13"|"13b"|"14"|"15"|"16"|"17"|"18"|"19"|"20"|"21"|"22":
            return 4
        case "23":
            return 5
        case "24"|"25"|"26"|"27"|"28"|"29"|"30"|"31"|"32"|"33":
            return 6
        case "34"|"34a"|"35"|"36"|"37"|"38"|"39"|"40"|"41"|"42":
            return 7
        case "43"|"43a":
            return 8
        case "44"|"45"|"45a":
            return 9
        case "46"|"47"|"48"|"49"|"50"|"51"|"52"|"53"|"54"|"55"|"56"|"57"|"58"|"59"|"60":
            return 10
        case "60a":
            return 11
        case "61"|"62"|"63"|"64"|"64a"|"65"|"65a"|"66"|"67"|"67a"|"68"|"69"|"70"|"71"|"72"|"73"|"74"|"75":
            return 12
        case "76"|"77"|"78"|"78a"|"79"|"80"|"81"|"82"|"83"|"84"|"85"|"86"|"87"|"88"|"89"|"90"|"91"|"92"|"93"|"94":
            return 13
        case "21a":
            return "gimmick_1"
        case "30a":
            return "gimmick_2"
        case "56a":
            return "gimmick_3"
        case "93a":
            return "gimmick_4"
        case _:
            return default_palette # change default palette lole

def paths(canvas: str, user: int, mode: str):
    """A number of paths designed for Tib's specific use case."""
    palette = get_palette(canvas)
    bg = f"{pxlslog_explorer_dir}/pxls-canvas/canvas-{canvas}-initial-empty.png"
    palette_path = f"{pxlslog_explorer_dir}/pxls-palette/palette_{palette}.gpl"
    output_dir = f"{pxlslog_explorer_dir}/pxls-out-tib"
    output_path = f"{output_dir}/c{canvas}_{mode}_{user}.png"
    return bg, palette_path, output_path

def tpe(canvas: str):
    """All canvases TPE has been present on, for passing against images in /templates"""
    tpe_canvas = [
        "51", "52", "53", "54", "55", # before che
        "57", "58", "59", "60", "61", "63", "66", "67", "68", "77", "78a", # during che
        "81", "82", "83", "84", "85", "86", "87", "88", "88a", "89", "90", "91", "92", "93", "94", "95", "96", "97", "98", "99", "100"  # after che, expand with new canvases
        ]
    tpe_present = canvas.strip() in tpe_canvas
    return tpe_present

def ranks():
    """A list of tuples for pixels required & associated rank."""
    return [
        (150000, "Admiral"),
        (100000, "General"),
        (75000, "Colonel"),
        (50000, "Major"),
        (30000, "Sergeant Major"),
        (15000, "Sergeant"),
        (5000, "Corporal"),
        (1000, "Private"),
    ]