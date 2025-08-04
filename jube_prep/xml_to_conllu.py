import xml.etree.ElementTree as ET
import os
import pandas as pd
import json
import math
import shutil
import argparse

from jube_prep.utils import custom_split, remove_brackets, write_line, clean_csv


def process_jube(
    data_folder, input_folder, output_folder, copy_audio, need_clean_csv, limit
):
    if not os.path.exists(input_folder):
        os.makedirs(input_folder)

    media_folder = os.path.join(output_folder, "media")
    if not os.path.exists(media_folder):
        os.makedirs(media_folder)

    # copy meta.json to "input_folder"
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    meta_path = os.path.join(BASE_DIR, "meta.json")

    shutil.copy2(meta_path, input_folder)

    # Read the speaker metadata (maybe more accurate to call it "Tier metadata", where some Tiers are speakers)
    person_meta_path = data_folder + "/BE_2019_Personendaten.csv"
    if need_clean_csv:
        clean_csv(person_meta_path)

    person_meta = pd.read_csv(person_meta_path)
    person_meta["speaker_id"] = (
        person_meta["person_id"].str.strip().str.replace(" ", "_")
    )
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
    speaker_lookup_file = input_folder + "/global_attribute_speaker.csv"

    xml_files = [
        os.path.join(data_folder, file_name)
        for file_name in os.listdir(data_folder)
        if file_name.endswith(".xml")
    ]
    conllu_file_name = input_folder + "conllu_output.conllu"
    # open conllu file
    conllu_file = open(conllu_file_name, "w", encoding="UTF-8")
    # write common fields to conllu file
    print("# global.columns = ID FORM LEMMA MISC", file=conllu_file)
    doc_end_prev = 0
    for k, file_name in enumerate(xml_files):
        # if "010" in file_name or "009" in file_name:
        #     continue
        if k == limit:
            break
        tree = ET.parse(file_name)
        root = tree.getroot()

        time_order_values = {}

        time_order = root.find("TIME_ORDER")
        if time_order is not None:
            for time_slot in time_order.findall("TIME_SLOT"):
                time_slot_id = time_slot.get("TIME_SLOT_ID")
                time_value = time_slot.get("TIME_VALUE")
                time_order_values[time_slot_id] = round(
                    (int(time_value) / 1000), 2
                )  # milliseconds to seconds

            doc_end = math.ceil(max(time_order_values.values()))

        doc_id = os.path.basename(file_name).split(".")[0]
        # default audio file name
        audio_file_name = f"{doc_id.split('_T')[0]}_A.mp3"
        if copy_audio:
            audio_file_name = f"{doc_id.split('_T')[0]}_A.wav"

            # copy audio file to output/media folder
            audio_file_path = os.path.join(data_folder, audio_file_name)
            if os.path.exists(audio_file_path):
                audio_file_dest = os.path.join(media_folder, audio_file_name)
                shutil.copy2(audio_file_path, audio_file_dest)

        print(f"\n# newdoc id = {doc_id}", file=conllu_file)
        print(f"# newdoc audio = {audio_file_name}", file=conllu_file)
        print(f"# newdoc start = {doc_end_prev}", file=conllu_file)
        print(f"# newdoc end = {doc_end + doc_end_prev}", file=conllu_file)

        # start writing utterances to conllu file with corresponding fields
        tiers = root.findall("TIER")
        tier_ids = [tier.get("TIER_ID") for tier in tiers]
        for i, speaker in enumerate(tier_ids):
            subelements = root.findall(f"TIER[@TIER_ID='{speaker}']//*")
            speaker = speaker.strip().replace(" ", "_")

            if speaker not in person_meta["speaker_id"].values:
                # Add this speaker_id to person_meta with other fields as NaN
                new_row = pd.DataFrame({"speaker_id": [speaker]})
                person_meta = pd.concat([person_meta, new_row], ignore_index=True)

            ### check if it's a speaker ID or simply background noise/notes, etc.

            for subelement in subelements:
                background_speech = False
                if len(subelement.attrib) == 0:
                    continue
                utterance = subelement.attrib["ANNOTATION_ID"]
                text = subelement.find("ANNOTATION_VALUE").text
                if text is None or text.strip() == "":
                    continue

                start = time_order_values[subelement.attrib["TIME_SLOT_REF1"]]
                end = time_order_values[subelement.attrib["TIME_SLOT_REF2"]]

                segment_start = start + doc_end_prev
                segment_end = end + doc_end_prev

                # newline before each utterance for better readability
                print(f"\n# sent_id = {utterance}", file=conllu_file)
                print(f"# speaker_id = {speaker}", file=conllu_file)
                print(f"# start = {segment_start}", file=conllu_file)
                print(f"# end = {segment_end}", file=conllu_file)
                print(f"# text = {text}", file=conllu_file)

                if speaker not in person_meta["speaker_id"].values:
                    new_row = pd.DataFrame(
                        [{"speaker_id": speaker}]
                    )  # Create DataFrame with a list of dicts
                    person_meta = pd.concat([person_meta, new_row], ignore_index=True)

                for i, token in enumerate(custom_split(text)):
                    if len(token.split()) > 1 and "/" in token:
                        new_token_lst = [form.split("/")[0] for form in token.split()]
                        processed_token = " ".join(new_token_lst)
                        for form in processed_token.split():
                            form = remove_brackets(form)
                            if form is None:
                                continue
                            write_line(
                                form, i, (segment_start, segment_end), conllu_file
                            )

                    elif len(token.split()) > 1:
                        continue

                    else:
                        form = remove_brackets(token)
                        if form is None:
                            continue
                        write_line(form, i, (segment_start, segment_end), conllu_file)
        doc_end_prev += doc_end
    conllu_file.close()

    # Create a new DataFrame with the desired format
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
        sep=",",
        index=False,
        encoding="UTF-8",
    )


def main():
    """
    Handles command-line argument parsing and calls process_jube().
    """
    parser = argparse.ArgumentParser(description="Process JUBE corpus data")
    parser.add_argument(
        "--data_folder",
        default="./JUBEKO/JUBEKO/Datensatz/Datenerhebung_2019",
        help="Path to folder with corpus raw data",
    )
    parser.add_argument(
        "--input_folder",
        default="./input/",
        help="Path to the input folder that will contain CONLL-U file",
    )
    parser.add_argument(
        "--output_folder",
        default="./output/",
        help="Path to the output folder (to be uploaded to the platform)",
    )

    parser.add_argument(
        "--copy_audio",
        action="store_true",
        default=False,
        help="Copy original WAV audio files to the output/media folder",
    )

    parser.add_argument(
        "--clean_csv",
        action="store_true",
        default=False,
        help="Clean the person CSV file from empty rows and rename columns",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of files to process",
    )

    args = parser.parse_args()

    process_jube(
        args.data_folder,
        args.input_folder,
        args.output_folder,
        args.copy_audio,
        args.clean_csv,
        args.limit,
    )


# Ensures main() is only executed when running this script directly
if __name__ == "__main__":
    main()
