import xml.etree.ElementTree as ET
import os
import re
import pandas as pd
import json
import csv
import math
import uuid
from typing import Dict, Tuple
from tqdm import tqdm

# Ensure the output directory exists
output_dir = "./my_output/"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

person_meta = pd.read_csv("./Datensatz/Datenerhebung_2019/BE_2019_Personendaten.csv")
person_meta["speaker_id"] = person_meta["person_id"].str.strip().str.replace(" ", "_")
person_meta.rename(
    columns={
        "Gender": "gender",
        "Age": "age",
        "Place of birth": "birth_place",
        "Residence": "residence",
        "Living in Bern since": "living_in_bern_since",
        "Nationality": "nationality",
        "Education": "education",
        "Origin of parents": "parents_origin",
        "Mother tongue of parents": "parents_mother_tongue",
        "notes": "notes",
    },
    inplace=True,
)
person_meta["age"] = person_meta["age"].apply(
    lambda x: x.split("/")[0] if isinstance(x, str) and "/" in x else x
)


# Create a lookup file for speaker metadata
speaker_lookup_file = output_dir + "global_attribute_speaker.tsv"


def check_for_background(text):
    if text[0] == "(" and text[-1] == ")":
        if text[1:-1].isupper():
            return True
    elif "UNVERSTÄNDLICH" in text:
        return True
    return False


def check_pauses(text):
    if text[0] == "(" and text[-1] == ")" and all(char == "." for char in text[1:-1]):
        return True
    return False


def remove_brackets(seg):
    """
    Remove brackets from the segment if there is no content inside them. \n
    """
    seg = re.sub(r"\[\s*\]", "", seg)
    seg = re.sub(r"\s+", " ", seg)
    return seg


def check_for_notes(form):
    """
    Check if the form contains any notes and write them to the CONLL-U file. \n
    The notes come provided with the corpus.
    """

    # Determine annotation category
    category = "-"

    # Check for unintelligible speech
    if re.fullmatch(r"\((UNV.*ICH|unv.*ich|\?{1,3})\)", form):
        category = "unintelligible"

    elif form in ["(unverständlcih)", "(UMVERSTÄNDLICH)", "(unverständlch)"]:
        category = "unintelligible"

    # Check for multiple pronunciation variants
    elif re.fullmatch(r"\([a-z]+/[a-z]+\)", form):
        category = "multiple_variants"

    # Check for mimesis (non-linguistic sounds)
    elif re.fullmatch(r"\(+[A-ZÄÖÜ\s]+\)+", form):
        category = "mimesis"

    elif form in [
        "(gelächter)",
        "(lacht)",
        "(Biergeräusch)",
        "(lachen)",
        "((lacht))",
        "(weinen)",
        "(singend)",
        "((schmunzelt))",
        "(lippenflattern)",
    ]:  # add more
        category = "mimesis"

    elif re.fullmatch(r"\(+[a-zäöü\s]+\)+", form):
        category = "assumed_wording"

    # Check for pauses (including micropauses)
    elif re.fullmatch(r"\(\.{1,}\)", form) or re.fullmatch(r"\(\d+(\.\d+)?s?\)", form):
        category = "pause"

    # Check for truncated syllables
    elif re.fullmatch(r"\(.+\)", form):
        category = "other_note"

    # Check for anonymized names
    elif re.fullmatch(r".*XX{1,3}.*", form):
        if form == "MAXX":  # to account for erroneous hit
            category = "proper_name_abbreviation"
        else:
            category = "anonymized"

    # Check for hesitation sounds
    elif form in ["ehm", "eh", "mhm", "hm"]:
        category = "hesitation"

    # Check for elongated vowels
    elif re.search(r":{1,3}", form):
        category = "lengthening"

    # Check for proper names (all characters are capital)
    elif form.isupper():
        category = "proper_name_abbreviation"

    return category


def custom_split(text):
    # Regular expression pattern
    # Match either:
    # 1. Parentheses with any content, including adjacent non-whitespace characters
    # 2. Any sequence of non-whitespace characters
    pattern = r"\S*\([^()]*\)\S*|\S+"

    # Find all matches
    matches = re.findall(pattern, text)

    return matches


def process_token(form):
    alternative = None
    # Handle variant forms by taking the first part before '/'
    if "/" in form:
        variants = form.split("/")
        form = variants[0]
        # If there are multiple variants, save the alternative and return it additionally
        if len(variants) > 1:
            alternative = variants[1]

    # Remove any non-parenthesis brackets (assuming this doesn't strip parentheses)
    form = form.strip()

    return (form, alternative)


###############################################################

# Initialize CSV files
with open(
    "./my_output/document.csv", "w", encoding="utf-8", newline=""
) as doc_file, open(
    "./my_output/segment.csv", "w", encoding="utf-8", newline=""
) as seg_file, open(
    "./my_output/token.csv", "w", encoding="utf-8", newline=""
) as token_file, open(
    "./my_output/token_form.csv", "w", encoding="utf-8", newline=""
) as form_file, open(
    "./my_output/fts_vector.csv", "w", encoding="utf-8", newline=""
) as fts_vector_file:

    doc_writer = csv.writer(doc_file, delimiter="\t")
    seg_writer = csv.writer(seg_file, delimiter="\t")
    token_writer = csv.writer(token_file, delimiter="\t")
    form_writer = csv.writer(form_file, delimiter="\t")
    fts_vector_writer = csv.writer(fts_vector_file, delimiter="\t")

    # Write headers
    doc_writer.writerow(["document_id", "char_range", "frame_range", "media"])
    seg_writer.writerow(
        ["segment_id", "char_range", "frame_range", "speaker_id", "document_id"]
    )
    token_writer.writerow(
        ["token_id", "form_id", "char_range", "frame_range", "segment_id", "meta"]
    )
    form_writer.writerow(["form_id", "form"])
    fts_vector_writer.writerow(["segment_id", "vector"])

    # Initialize global counters
    prev_char_end = 0
    prev_seconds_end = 0
    form_to_id: Dict[str, int] = {}
    current_form_id = 1

    folder_path = "Datensatz/Datenerhebung_2019/"
    xml_files = [
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if f.endswith(".xml")
    ]

    for file_name in xml_files[:6]:  # Process first 5 files for testing
        tree = ET.parse(file_name)
        root = tree.getroot()
        doc_id = os.path.basename(file_name).split(".")[0]

        # Process time slots
        time_order = root.find("TIME_ORDER")
        time_order_values = {}
        if time_order is not None:
            for time_slot in time_order.findall("TIME_SLOT"):
                time_slot_id = time_slot.get("TIME_SLOT_ID")
                time_value = time_slot.get("TIME_VALUE")
                if time_value:
                    time_order_values[time_slot_id] = round(int(time_value) / 1000, 2)
            doc_end = math.ceil(max(time_order_values.values(), default=0))
        else:
            doc_end = 0

        # Collect valid segments
        segments = []
        current_doc_char_length = 0
        for tier in root.findall("TIER"):
            speaker_id = tier.get("TIER_ID").strip().replace(" ", "_")
            for annot in tier.findall(".//ALIGNABLE_ANNOTATION"):
                text_elem = annot.find("ANNOTATION_VALUE")
                if text_elem is None or text_elem.text is None:
                    continue
                text = text_elem.text.strip()
                text = remove_brackets(text)

                ### Skip if segment has only background/pauses # NOTE: is this necessary?
                # if check_for_background(text) or check_pauses(text):
                #     continue

                # Get time values
                start_time = time_order_values.get(annot.get("TIME_SLOT_REF1"), 0)
                end_time = time_order_values.get(annot.get("TIME_SLOT_REF2"), 0)

                segments.append(
                    {
                        "text": text,
                        "speaker_id": speaker_id,
                        "start_time": start_time,
                        "end_time": end_time,
                        "char_length": len(text),
                    }
                )
                current_doc_char_length += len(text)

        # Document metadata
        audio_file = f"{doc_id.split('_T')[0]}_A.wav"
        doc_char_range = (prev_char_end, prev_char_end + current_doc_char_length)
        doc_seconds_range = (prev_seconds_end, prev_seconds_end + doc_end)
        doc_frames_range = (
            int(round(doc_seconds_range[0] * 25)),
            int(round(doc_seconds_range[1] * 25)),
        )
        json_str = "{" + f"audio: {audio_file}" + "}"
        doc_writer.writerow(
            [
                doc_id,
                f"[{doc_char_range[0]}, {doc_char_range[1]})",
                f"[{doc_frames_range[0]}, {doc_frames_range[1]})",
                json_str,
            ],
        )

        # Process segments
        cumulative_char = prev_char_end
        for seg in segments:
            seg_id = str(uuid.uuid4())

            # Calculate character range
            seg_char_start = cumulative_char
            seg_char_end = cumulative_char + seg["char_length"]
            cumulative_char = seg_char_end

            # Calculate time range
            seg_seconds_start = prev_seconds_end + seg["start_time"]
            seg_frames_start = int(round(seg_seconds_start * 25, 0))
            seg_seconds_end = prev_seconds_end + seg["end_time"]
            seg_frames_end = int(round(seg_seconds_end * 25, 0))

            # Write segment data
            seg_writer.writerow(
                [
                    seg_id,
                    f"[{seg_char_start}, {seg_char_end})",
                    f"[{seg_frames_start}, {seg_frames_end})",
                    seg["speaker_id"],
                    doc_id,
                ]
            )

            # Process tokens
            forms = []
            alternative_forms = []
            token_vector = []
            for n, token in enumerate(custom_split(seg["text"]), start=1):
                # Implement your token processing logic here
                processed_form, alternative = process_token(token)
                if alternative:
                    alternative_forms.append(alternative.strip(")"))
                    processed_form = processed_form.strip("(")
                else:
                    alternative_forms.append("-")
                forms.append(processed_form)
                token_vector.append(
                    f"'1{processed_form}':{n}"
                )  # write to fts_vector file
            token_vector = " ".join(token_vector)
            fts_vector_writer.writerow([seg_id, token_vector])

            # Calculate token positions
            current_pos = 0
            token_ranges = []
            for i, form in enumerate(forms):
                start = current_pos
                end = start + len(form)
                token_ranges.append((start, end))
                current_pos = end + 1 if i < len(forms) - 1 else end

            # Write tokens
            for i, (form, (start, end)) in enumerate(zip(forms, token_ranges)):
                if form not in form_to_id:
                    form_to_id[form] = current_form_id
                    current_form_id += 1

                meta_str = (
                    "{"
                    + f"alternative: {alternative_forms[i]}, "
                    + f"note: {check_for_notes(form)}"
                    + "}"
                )

                token_writer.writerow(
                    [
                        str(uuid.uuid4()),
                        form_to_id[form],
                        f"[{seg_char_start + start}, {seg_char_start + end})",
                        f"[{seg_frames_start}, {seg_frames_end})",
                        seg_id,
                        meta_str,
                    ]
                )

        # Update global counters
        prev_char_end += current_doc_char_length
        prev_seconds_end += doc_end

    for form, form_id in form_to_id.items():
        form_writer.writerow([form_id, form])

person_meta_formatted = pd.DataFrame()
person_meta_filled = person_meta.fillna("")
person_meta_formatted["speaker_id"] = person_meta_filled["speaker_id"]
person_meta_formatted["speaker"] = person_meta_filled.drop(
    columns=["speaker_id", "person_id", "birth_place"]
).apply(lambda row: json.dumps(row.to_dict(), ensure_ascii=False), axis=1)
# Remove duplicates from person_meta_formatted
person_meta_formatted.drop_duplicates(subset=["speaker_id"], inplace=True)

# Write to TSV file
person_meta_formatted.to_csv(
    speaker_lookup_file,
    sep="\t",
    index=False,
    quoting=csv.QUOTE_NONE,
    escapechar="\\",
    encoding="UTF-8",
)
