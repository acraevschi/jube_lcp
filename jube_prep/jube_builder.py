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
    get_token_note,
    clean_empty_lines_in_output,
    normalize_speaker_id,
    clean_speaker_age,
)


# keep only the normalized string id (first item of the tuple)
def sid(x: str) -> str:
    return normalize_speaker_id(str(x))[0]


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

    # keep age as int before renaming columns
    person_meta["Age"] = person_meta["Age"].apply(clean_speaker_age).astype(int)

    # Lowercase and replace spaces with underscores in column names
    person_meta.columns = person_meta.columns.str.lower().str.replace(" ", "_")

    # normalized speaker id (string, not tuple)
    person_meta["speaker_id"] = person_meta["person_id"].apply(sid)

    person_meta = person_meta.drop_duplicates(
        subset=["speaker_id"], keep="first"
    ).reset_index(drop=True)

    # Create global speaker attributes
    speakers = {}
    for _, row in person_meta.iterrows():
        speaker_id = row["speaker_id"]  # string id
        attrs = {"id": speaker_id}
        attrs.update(
            {col: row[col] for col in person_meta.columns if col != "speaker_id"}
        )
        if "person_id" not in attrs or attrs.get("person_id", "") == "":
            attrs["person_id"] = speaker_id
        if speaker_id not in speakers:
            speakers[speaker_id] = corpus.Speaker(attrs)

    # Helper to create a default/unknown speaker on the fly
    def ensure_speaker_exists(spk_id: str):
        if spk_id not in speakers:
            attrs = {"id": spk_id, "person_id": spk_id}
            # include all metadata fields with empty defaults, except "speaker_id" and "age"
            for key in person_meta.columns:
                if key not in ("speaker_id", "age", "person_id"):
                    attrs[key] = ""
            attrs["age"] = -1
            speakers[spk_id] = corpus.Speaker(attrs)
        return speakers[spk_id]

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
            if os.path.exists(src):
                shutil.copy2(src, dst)

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
                time_slots[slot_id] = time_ms / 1000.0  # seconds

        # Process linguistic tiers
        for tier in root.findall("TIER"):
            tier_id = tier.get("TIER_ID")
            layer_name, original_speaker_id = normalize_speaker_id(tier_id)

            for anno in tier.findall(".//ALIGNABLE_ANNOTATION"):
                text_elem = anno.find("ANNOTATION_VALUE")
                if (
                    text_elem is None
                    or text_elem.text is None
                    or text_elem.text.strip() == ""
                ):
                    continue

                text = text_elem.text.strip()
                start = time_slots[anno.get("TIME_SLOT_REF1")]
                end = time_slots[anno.get("TIME_SLOT_REF2")]

                # Convert times to frames (25fps)
                start_frame = int(start * 25)
                end_frame = int(end * 25)
                if start_frame <= end_frame:
                    end_frame += 1
                abs_start = start_frame + doc_end_prev
                abs_end = end_frame + doc_end_prev

                # ----- Recording-level layers: Notes / BackgroundNoise -----
                if layer_name in ("Notes", "BackgroundNoise"):
                    if layer_name == "Notes":
                        # resolve the referenced speaker
                        spk_key = (
                            sid(original_speaker_id) if original_speaker_id else None
                        )
                        speaker_ref = (
                            ensure_speaker_exists(spk_key) if spk_key else None
                        )
                        annotation = recording.Notes(text=text, speaker=speaker_ref)
                    else:
                        annotation = recording.BackgroundNoise(text=text)
                    annotation.set_time(abs_start, abs_end)
                    annotation.make()
                    continue  # very important

                # ----- Regular speaker tier -----
                speaker_id = sid(layer_name)
                speaker_ref = ensure_speaker_exists(speaker_id)

                # Create sentence
                sentence = recording.Sentence()
                sentence.speaker = speaker_ref
                sentence.original = text
                sentence.set_time(abs_start, abs_end)

                # Tokenize and process words
                clean_tokens = []
                notes_for_tokens = []

                for token in custom_split(text):
                    clean_token = remove_brackets(
                        token
                    )  # if it's just a note, becomes ""
                    if not clean_token:
                        continue  # do not create token for pure notes
                    note_val = get_token_note(token) or ""  # never None
                    clean_tokens.append(clean_token)
                    notes_for_tokens.append(note_val)

                # Calculate word times only if we have valid tokens
                if clean_tokens:
                    total_chars = sum(len(t) for t in clean_tokens)
                    total_frames = abs_end - abs_start
                    current_frame = abs_start

                    for i, (clean_token, note_val) in enumerate(
                        zip(clean_tokens, notes_for_tokens)
                    ):
                        token_ratio = (
                            len(clean_token) / total_chars if total_chars else 0
                        )
                        token_duration = round(token_ratio * total_frames)

                        token_end = (
                            abs_end
                            if i == len(clean_tokens) - 1
                            else current_frame + token_duration
                        )

                        # Create word; attach "note" only when there is a note
                        if note_val:
                            word = sentence.Word(clean_token, note=note_val)
                        else:
                            word = sentence.Word(clean_token)

                        if current_frame >= token_end:
                            word.set_time(token_end - 1, token_end)
                        else:
                            word.set_time(current_frame, token_end)

                        current_frame = token_end

                sentence.make()

        recording.make()
        doc_end_prev = recording.get_time()[-1]

    # Finalize corpus
    corpus.make(output_folder)

    # Remove spurious empty lines produced on some platforms
    clean_empty_lines_in_output(output_folder)

    # Add tracks config to split Sentence by speaker
    config_path = os.path.join(output_folder, "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except UnicodeDecodeError:
        with open(config_path, "r") as f:
            config = json.load(f)

    config["tracks"] = {
        "layers": {
            "Notes": {},
            "BackgroundNoise": {},
            "Sentence": {"split": ["speaker"]},
        }
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


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
