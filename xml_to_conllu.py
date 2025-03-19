import xml.etree.ElementTree as ET
import os
import re
import pandas as pd
import json
import math

conllu_folder = "./conllu_files/"
if not os.path.exists(conllu_folder):
    os.makedirs(conllu_folder)

# Read the speaker metadata (maybe more accurate to call it "Tier metadata", where some Tiers are speakers)
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
speaker_lookup_file = conllu_folder + "/global_attribute_speaker.csv"


def remove_brackets(seg):
    """
    Remove brackets from the segment if there is no content inside them. \n
    """
    seg = re.sub(r"\[\s*\]", "", seg)
    seg = re.sub(r"\s+", " ", seg)
    return seg


def write_line(form, i, time_ranges, conllu_file):
    """
    Writes a line to the CONLL-U file. \n
    Figures out the annotation category of the form (if there is one) and writes it to the file. \n
    """
    # Handle variant forms by taking the first part before '/'
    if "/" in form:
        form = form.split("/")[0]
    start_token, end_token = time_ranges
    # Remove any non-parenthesis brackets (assuming this doesn't strip parentheses)
    form = remove_brackets(form)

    form_id = i + 1

    # Determine annotation category
    category = "-"
    form = form.strip()

    # Check for unintelligible speech
    if re.fullmatch(r"\((UNV.*ICH|unv.*ich|\?{1,3})\)", form):
        category = "unintelligible"

    # spotted a few more variations of unintelligible speech with typos:
    elif form in ["(unverständlcih)", "(UMVERSTÄNDLICH)", "(unverständlch)"]:
        category = "unintelligible"

    # Check for multiple pronunciation variants (maybe save alternatives?)
    elif re.fullmatch(r"\([a-z]+/[a-z]+\)", form):
        category = "multiple_variants"

    # Check for mimesis
    elif re.fullmatch(r"\(+[A-ZÄÖÜ\s]+\)+", form):
        category = "mimesis"

    # More mimesis with variable capitalization
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
        "(ha)",
    ]:
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

    # Write to CONLL-U file
    print(
        f"{form_id}\t{form}\t{form}\tnote={category}|start={start_token}|end={end_token}",
        file=conllu_file,
    )


def custom_split(text):
    # Regular expression pattern
    # Match either:
    # 1. Parentheses with any content, including adjacent non-whitespace characters
    # 2. Any sequence of non-whitespace characters
    pattern = r"\S*\([^()]*\)\S*|\S+"

    # Find all matches
    matches = re.findall(pattern, text)

    return matches


folder_path = "Datensatz/Datenerhebung_2019/"
xml_files = [
    os.path.join(folder_path, file_name)
    for file_name in os.listdir(folder_path)
    if file_name.endswith(".xml")
]
conllu_file_name = conllu_folder + "conllu_output.conllu"
# open conllu file
conllu_file = open(conllu_file_name, "w", encoding="UTF-8")
# write common fields to conllu file
print("# global.columns = ID FORM LEMMA MISC", file=conllu_file)
doc_end_prev = 0
for k, file_name in enumerate(xml_files):
    if k == 1:  # temporary to test
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

    # conllu_file_name = os.path.basename(file_name).replace(".xml", ".conllu")
    # conllu_file_name = conllu_folder + conllu_file_name
    # with open(conllu_file_name, "w", encoding="UTF-8") as conllu_file:
    doc_id = os.path.basename(file_name).split(".")[0]
    audio_file_name = f"{doc_id.split('_T')[0]}_A.wav"
    # write common fields to conllu file
    # print("# global.columns = ID FORM MISC", file=conllu_file)
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
        # match_speaker_pattern = r"^T\d+(\.\d+)?_GP\d+$"
        # if not bool(re.match(match_speaker_pattern, speaker)):
        #     continue  # if not, skip to the next iteration
        for subelement in subelements:
            background_speech = False
            if len(subelement.attrib) == 0:
                continue
            utterance = subelement.attrib["ANNOTATION_ID"]
            text = subelement.find("ANNOTATION_VALUE").text
            if text is None:
                continue
            start = time_order_values[subelement.attrib["TIME_SLOT_REF1"]]
            end = time_order_values[subelement.attrib["TIME_SLOT_REF2"]]

            segment_start = start + doc_end_prev
            segment_end = end + doc_end_prev

            print(
                f"\n# sent_id = {utterance}", file=conllu_file
            )  # newline before each utterance for better readability
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
                        write_line(form, i, (segment_start, segment_end), conllu_file)

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
