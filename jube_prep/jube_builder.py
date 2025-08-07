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
    normalize_speaker_id,
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
        document="Recording",
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
    person_meta = person_meta.fillna("")
    person_meta["speaker_id"] = person_meta["person_id"].apply(normalize_speaker_id)

    # Create global speaker attributes
    speakers = {}
    for _, row in person_meta.iterrows():
        speaker_id = row["speaker_id"]
        # Add 'id' field with person_id value
        attrs = {"id": speaker_id}  # Add this first
        # Add other attributes
        attrs.update(
            {col: row[col] for col in person_meta.columns if col != "speaker_id"}
        )
        # Create global attribute
        speakers[speaker_id] = corpus.Speaker(attrs)

    # Process XML files
    xml_files = [f for f in os.listdir(data_folder) if f.endswith(".xml")]
    doc_end_prev = 0
    for xml_file in tqdm(xml_files[:limit]):
        tree = ET.parse(os.path.join(data_folder, xml_file))
        root = tree.getroot()
        doc_id = os.path.splitext(xml_file)[0]

        # Media handling
        audio_file = (
            f"{doc_id.split('_T')[0]}_A.wav"
            if copy_audio
            else f"{doc_id.split('_T')[0]}_A.mp3"
        )
        if copy_audio:
            src = os.path.join(data_folder, audio_file)
            dst = os.path.join(media_folder, audio_file)
            shutil.copy2(src, dst) if os.path.exists(src) else None

        # Create document (Recording)
        recording = corpus.Recording(name=doc_id)
        recording.set_media("audio", audio_file)

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
            speaker_id = normalize_speaker_id(tier.get("TIER_ID"))

            # Add new speakers to metadata (with 'id' field)
            if speaker_id not in speakers:
                attrs = {"id": speaker_id}  # Add 'id' field
                attrs.update(
                    {key: "" for key in person_meta.columns if key != "speaker_id"}
                )
                attrs["person_id"] = speaker_id  # Ensure person_id is set
                speakers[speaker_id] = corpus.Speaker(attrs)

            # Process annotations
            for anno in tier.findall(".//ALIGNABLE_ANNOTATION"):
                text_elem = anno.find("ANNOTATION_VALUE")
                if text_elem.text is None or text_elem.text.strip() == "":
                    continue

                text = text_elem.text.strip()
                start = time_slots[anno.get("TIME_SLOT_REF1")]
                end = time_slots[anno.get("TIME_SLOT_REF2")]

                # Create sentence
                sentence = recording.Sentence()
                sentence.speaker = speakers[speaker_id]
                sentence.original = text

                ### Doesn't accomodate word timing:
                # # Convert times to frames (25fps)
                # start_time, end_time = int(start * 25), int(end * 25)
                # if start_time <= end_time:
                #     end_time += 1
                # sentence.set_time(start_time + doc_end_prev, end_time + doc_end_prev)

                # # Tokenize and add words
                # for token in custom_split(text):
                #     clean_token = remove_brackets(token)
                #     if not clean_token:
                #         continue
                #     category = get_token_category(token)
                #     sentence.Word(clean_token, category=category)

                ### Accomodates word timing:
                # Convert times to frames (25fps)
                start_frame = int(start * 25)
                end_frame = int(end * 25)
                if start_frame <= end_frame:
                    end_frame += 1
                abs_start = start_frame + doc_end_prev
                abs_end = end_frame + doc_end_prev

                # Tokenize and process words
                tokens = []
                clean_tokens = []
                categories = []
                for token in custom_split(text):
                    clean_token = remove_brackets(token)
                    if not clean_token:
                        continue
                    category = get_token_category(token)
                    tokens.append(token)
                    clean_tokens.append(clean_token)
                    categories.append(category)

                # Set sentence time (absolute timeline)
                sentence.set_time(abs_start, abs_end)

                # Calculate word times only if we have valid tokens
                if clean_tokens:
                    total_chars = sum(len(t) for t in clean_tokens)
                    total_frames = abs_end - abs_start
                    current_frame = abs_start

                    for i, (clean_token, category) in enumerate(
                        zip(clean_tokens, categories)
                    ):
                        # Calculate proportional duration for this token
                        token_ratio = len(clean_token) / total_chars
                        token_duration = round(token_ratio * total_frames)

                        # Handle last token separately to account for rounding errors
                        if i == len(clean_tokens) - 1:
                            token_end = abs_end
                        else:
                            token_end = current_frame + token_duration

                        # Create word with calculated time span
                        word = sentence.Word(clean_token, category=category)

                        if current_frame >= token_end:
                            word.set_time(token_end - 1, token_end)
                        else:
                            word.set_time(current_frame, token_end)

                        # Move current frame pointer forward
                        current_frame = token_end

                sentence.make()
        recording.make()
        doc_end_prev = recording.get_time()[-1]

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

    # check for duplicate speaker IDs
    output_global_attribute = pd.read_csv("output/global_attribute_speaker.csv")
    removed_duplicates = output_global_attribute[
        ~output_global_attribute.duplicated(subset=["speaker_id"], keep="first")
    ]
    removed_duplicates.to_csv("output/global_attribute_speaker.csv", index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        default="./JUBEKO/JUBEKO/Datensatz/Datenerhebung_2019",
        help="Input data directory",
    )
    parser.add_argument(
        "--output",
        default="./output",
        help="Output directory for LCP corpus",
    )
    parser.add_argument(
        "--metadata",
        default="./meta.json",
        type=str,
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


if __name__ == "__main__":
    main()
