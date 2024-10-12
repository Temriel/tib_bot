#!/bin/bash
# generate.sh

set -ex

get_palette() {
    local CANVAS="$1"
    case "$CANVAS" in
        "1"|"2")
            echo "1"
            ;;
        "3"|"4"|"5"|"6"|"7")
            echo "2"
            ;;
        "8"|"9"|"10"|"11")
            echo "3"
            ;;
        "12"|"13"|"13b"|"14"|"15"|"16"|"17"|"18"|"19"|"20"|"21"|"22")
            echo "4"
            ;;
        "23")
            echo "5"
            ;;
        "24"|"25"|"26"|"27"|"28"|"29"|"30"|"31"|"32"|"33")
            echo "6"
            ;;        
        "34"|"34a"|"35"|"36"|"37"|"38"|"39"|"40"|"41"|"42")
            echo "7"
            ;;       
        "43"|"43a")
            echo "8"
            ;;
        "44"|"45"|"45a")
            echo "9"
            ;;
        "46"|"47"|"48"|"49"|"50"|"51"|"52"|"53"|"54"|"55"|"56"|"57"|"58"|"59"|"60")
            echo "10"
            ;;        
        "60a")
            echo "11"
            ;;       
        "61"|"62"|"63"|"64"|"64a"|"65"|"65a"|"66"|"67"|"67a"|"68"|"69"|"70"|"71"|"72"|"73"|"74"|"75")
            echo "12"
            ;;
        "76"|"77"|"78"|"78a"|"79"|"80"|"81"|"82"|"83"|"84")
            echo "13"
            ;;              
        "21a")
            echo "gimmick_1"
            ;;
        "30a")
            echo "gimmick_2"
            ;;
        "56a")
            echo "gimmick_3" # to add another, just copy paste (idk how to do this more efficiently)
            ;;
        *)
            echo "DEFAULT_PALATTE" # this covers everything beyond c84 (if the palette remians the same) 
            ;;
    esac
}

DEFAULT_PALATTE="13" # REMINDER to change this 

CANVAS=$1
USER=$2
USER_KEY=$3
BG="--bg D:/pxlslog-explorer/target/release/pxls-canvas/canvas-${CANVAS}-initial-empty.png"
PALETTE="--palette D:/pxlslog-explorer/target/release/pxls-palette/palette_$(get_palette "$CANVAS").gpl"
OUTPUT_DIR="D:/pxlslog-explorer/target/release/pxls-out-tib"
OUTPUT_FILE="${OUTPUT_DIR}/c${CANVAS}_normal_${USER}.png"

if [[ "$USER_KEY" =~ ^[a-z0-9]{512}$ ]]; then
    echo "Error: Invalid user key format."
    exit 1
fi

if [[ "$CANVAS" =~ ^(?![cC])[a-z0-9]+$ ]]; then
    echo "Error: Invalid canvas number."
    exit 1
fi

if [ ! -f "D:/pxlslog-explorer/target/release/filter.exe" ]; then
    echo "filter.exe not found!"
    exit 1
fi

if [ ! -f "D:/pxlslog-explorer/target/release/render.exe" ]; then
    echo "render.exe not found!"
    exit 1
fi

if [ ! -d "$OUTPUT_DIR" ]; then
    mkdir -p "$OUTPUT_DIR"
    chmod 755 "$OUTPUT_DIR"
fi

echo "Generating a placemap for $USER on canvas $CANVAS."

D:/pxlslog-explorer/target/release/filter.exe -v --user ${USER_KEY} --log D:/pxlslog-explorer/target/release/pxls-logs/pixels_c${CANVAS}.sanit.log --output D:/pxlslog-explorer/target/release/pxls-userlogs-tib/${USER}_pixels_c${CANVAS}.log
D:/pxlslog-explorer/target/release/render.exe --log D:/pxlslog-explorer/target/release/pxls-userlogs-tib/${USER}_pixels_c${CANVAS}.log ${BG} ${PALETTE} --screenshot --output "$OUTPUT_FILE"

chmod 644 "$OUTPUT_FILE"