import xml.etree.ElementTree as ET
import os
import pandas as pd
import json
import shutil
import argparse
from tqdm import tqdm
from lcpcli.builder import Corpus

from jube_prep.utils import (
    custom_split,
    remove_brackets,
    clean_csv,
    get_token_category,
    clean_empty_lines_in_output,
)


def process_jube(
    data_folder,
    output_folder,
    metadata,
    copy_audio=False,
    need_clean_csv=False,
    limit=None,
):
    with open(metadata, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # Setup output directories
    media_folder = os.path.join(output_folder, "media")
    os.makedirs(media_folder, exist_ok=True)
    os.makedirs(output_folder, exist_ok=True)

    # Initialize LCP corpus
    corpus = Corpus(
        name=meta["name"],
        document="Clip",
        segment="Sentence",
        token="Word",
        description=meta["description"],
        date=meta["date"],
        revision=meta["revision"],
        authors=meta["authors"],
    )

    # Load speaker metadata and create global attributes
    person_meta_path = os.path.join(data_folder, "BE_2019_Personendaten.csv")
    if need_clean_csv:
        clean_csv(person_meta_path)

    person_meta = pd.read_csv(person_meta_path)
    person_meta["speaker_id"] = (
        person_meta["person_id"].str.strip().str.replace(" ", "_")
    )
    person_meta = person_meta.fillna("")

    # Create global speaker attributes
    speakers = {}
    for _, row in person_meta.iterrows():
        speaker_id = row["speaker_id"]
        # Create attribute dictionary from row
        attrs = {col: row[col] for col in person_meta.columns if col != "speaker_id"}
        # Create global attribute
        speakers[speaker_id] = corpus.Speaker(attrs)

    # Process XML files
    xml_files = [f for f in os.listdir(data_folder) if f.endswith(".xml")]
    doc_end_prev = 0
    for xml_file in tqdm(xml_files[:limit]):
        # Parse XML structure
        tree = ET.parse(os.path.join(data_folder, xml_file))
        root = tree.getroot()
        doc_id = os.path.splitext(xml_file)[0]

        # Create media reference
        audio_file = (
            f"{doc_id.split('_T')[0]}_A.wav"
            if copy_audio
            else f"{doc_id.split('_T')[0]}_A.mp3"
        )
        if copy_audio:
            src = os.path.join(data_folder, audio_file)
            dst = os.path.join(media_folder, audio_file)
            shutil.copy2(src, dst) if os.path.exists(src) else None

        # Create document (Clip) in corpus
        clip = corpus.Clip(name=doc_id)
        clip.set_media("audio", audio_file)

        # Process time slots
        time_slots = {}
        time_order = root.find("TIME_ORDER")
        if time_order is not None:
            for slot in time_order.findall("TIME_SLOT"):
                slot_id = slot.get("TIME_SLOT_ID")
                time_ms = int(slot.get("TIME_VALUE"))
                time_slots[slot_id] = time_ms / 1000.0  # Convert to seconds

        # Process linguistic tiers
        for tier in root.findall("TIER"):
            speaker_id = tier.get("TIER_ID").strip().replace(" ", "_")

            # Add new speakers to metadata
            if speaker_id not in speakers:
                attrs = {key: "" for key in person_meta.columns if key != "speaker_id"}
                attrs["person_id"] = speaker_id
                speakers[speaker_id] = corpus.Speaker(attrs)

            # Process annotations (sentences)
            for anno in tier.findall(".//ALIGNABLE_ANNOTATION"):
                text_elem = anno.find("ANNOTATION_VALUE")
                if text_elem.text is None:
                    continue
                elif text_elem.text.strip() == "":
                    continue

                text = text_elem.text.strip()
                start = time_slots[anno.get("TIME_SLOT_REF1")]
                end = time_slots[anno.get("TIME_SLOT_REF2")]

                # Create sentence with metadata
                sentence = clip.Sentence()
                sentence.speaker = speakers[speaker_id]
                sentence.original = text

                start_time, end_time = int(start * 25), int(
                    end * 25
                )  # Convert to frames (25fps)
                if start_time <= end_time:
                    end_time += 1
                sentence.set_time(start_time + doc_end_prev, end_time + doc_end_prev)

                # Tokenize and add words
                for token in custom_split(text):
                    clean_token = remove_brackets(token)
                    if not clean_token:
                        continue
                    category = get_token_category(token)
                    sentence.Word(clean_token, category=category)

                sentence.make()
        clip.make()
        doc_end_prev = clip.get_time()[-1]

    # Finalize corpus
    corpus.make(output_folder)

    # at least on Windows the output is produced with empty lines in-between the normal lines, need to clean it
    clean_empty_lines_in_output(output_folder)

    ### We need to add the "tracks" key to the config.json file
    config_path = os.path.join(output_folder, "config.json")
    # Load the created configuration.
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except UnicodeDecodeError:
        with open(config_path, "r") as f:
            config = json.load(f)

    # Add the "tracks" key.
    config["tracks"] = {"layers": {"Sentence": {"split": ["speaker"]}}}
    # Save the updated configuration.
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        default="./JUBEKO/JUBEKO/Datensatz/Datenerhebung_2019",
        required=True,
        help="Input data directory",
    )
    parser.add_argument(
        "--output",
        default="./output",
        required=True,
        help="Output directory for LCP corpus",
    )
    parser.add_argument(
        "--metadata",
        default="./meta.json",
        type=str,
        required=True,
        help="JSON string with corpus metadata (description, date, revision, authors)",
    )
    parser.add_argument(
        "--copy_audio", default=False, action="store_true", help="Copy audio files"
    )
    parser.add_argument(
        "--clean_csv", default=False, action="store_true", help="Clean metadata CSV"
    )
    parser.add_argument(
        "--limit", default=None, type=int, help="Limit number of files processed"
    )
    args = parser.parse_args()

    process_jube(
        args.data,
        args.output,
        args.metadata,
        copy_audio=args.copy_audio,
        need_clean_csv=args.clean_csv,
        limit=args.limit,
    )
