#! /bin/bash
if [ "${#FROM_MEMORY_IMAGE_FILENAME}" -lt 1 ]; then
    echo "No memory image filename given by ${FROM_MEMORY_IMAGE_FILENAME}, skipping memory analysis"
    exit 0
fi

PLUGINS=$MEMORY_PLUGINS

RUN_NAME="${FROM_MEMORY_IMAGE_FILENAME}__${TO_MEMORY_IMAGE_FILENAME}"
RUN_DIR="/results/memory/$RUN_NAME"
FROM_OUTPUT_PATH_TEMPLATE="$RUN_DIR/from"
TO_OUTPUT_PATH_TEMPLATE="$RUN_DIR/to"
mkdir -p "$RUN_DIR"

for plugin in $PLUGINS; do

    FROM_OUTPUT_FILENAME="$FROM_OUTPUT_PATH_TEMPLATE-$plugin.json"
    TO_OUTPUT_FILENAME="$TO_OUTPUT_PATH_TEMPLATE-$plugin.json"

    if [ ! -s "$FROM_OUTPUT_FILENAME" ]; then
        volatility3 --cache-path ./volatilitycache -o . -f "/snapshots/$FROM_MEMORY_IMAGE_FILENAME" --renderer json $plugin | tee "$FROM_OUTPUT_FILENAME"
    fi

    if [ ! -s "$TO_OUTPUT_FILENAME" ]; then
        volatility3 --cache-path ./volatilitycache -o . -f "/snapshots/$TO_MEMORY_IMAGE_FILENAME" --renderer json $plugin | tee "$TO_OUTPUT_FILENAME"
    fi
done
