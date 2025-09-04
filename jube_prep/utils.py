import re
import pandas as pd
import os


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
    The annotation categories are supposed to be easily searchable and filterable. \n
    But due to some incosistencies in the transcriptions and use of of brackets, it's challenging to identify and categorize all of them. \n
    In theory, it should correspond to GAT-2 standard
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


def get_token_note(form):
    """Categorize tokens based on linguistic patterns"""
    if re.fullmatch(r"\((UNV.*ICH|unv.*ich|\?{1,3})\)", form):
        return "unintelligible"
    elif form in ["(unverständlcih)", "(UMVERSTÄNDLICH)", "(unverständlch)"]:
        return "unintelligible"
    elif re.fullmatch(r"\([a-z]+/[a-z]+\)", form):
        return "multiple_variants"
    elif re.fullmatch(r"\(+[A-ZÄÖÜ\s]+\)+", form) or form in [
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
        return "mimesis"
    elif re.fullmatch(r"\(+[a-zäöü\s]+\)+", form):
        return "assumed_wording"
    elif re.fullmatch(r"\(\.{1,}\)", form) or re.fullmatch(r"\(\d+(\.\d+)?s?\)", form):
        return "pause"
    elif re.fullmatch(r"\(.+\)", form):
        return "other_note"
    elif re.fullmatch(r".*XX{1,3}.*", form) and form != "MAXX":
        return "anonymized"
    elif form in ["ehm", "eh", "mhm", "hm"]:
        return "hesitation"
    elif re.search(r":{1,3}", form):
        return "lengthening"
    elif form.isupper():
        return "proper_name_abbreviation"
    return "-"


def clean_csv(person_meta_path):
    header = [
        "person_id",
        "Gender",
        "Age",
        "Place of birth",
        "Residence",
        "Living in Bern since",
        "Nationality",
        "Education",
        "Origin of parents",
        "Mother tongue of parents",
        "notes",
    ]

    # Read the CSV file, skipping the first few rows with irrelevant data
    df = pd.read_csv(person_meta_path, skiprows=4, header=None)

    # Set the correct header
    df.columns = header

    # Save the cleaned CSV file
    df.to_csv(person_meta_path, index=False)

    print(f"Cleaned CSV file saved to: {person_meta_path}")


def clean_empty_lines_in_output(output_folder):
    """
    Process all CSV files in the output_folder. For each file, if an empty line
    is found and it is immediately followed by a non-empty line, delete the empty line.
    Otherwise (e.g. empty line at the end of the file), raise an error.
    """
    csv_files = [
        f"{output_folder}/{f}" for f in os.listdir(output_folder) if f.endswith(".csv")
    ]
    for csv_file in csv_files:
        try:
            with open(csv_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(csv_file, "r") as f:
                lines = f.readlines()

        new_lines = []
        for idx, line in enumerate(lines):
            if not line.strip():
                continue
            else:
                new_lines.append(line)

        # Write the cleaned file back only if changes were made.
        if new_lines != lines:
            with open(csv_file, "w", encoding="utf-8") as f:
                f.writelines(new_lines)


def normalize_speaker_id(speaker_id):
    """
    Normalizes speaker IDs, identifying special tiers like 'Notes' and 'Background_noise'.
    For 'Notes', it returns a tuple of ('Notes', original_speaker_id).
    For others, it returns a tuple of (normalized_id, None).
    """
    s = speaker_id.lower()
    # Map notes/comments variants
    if any(kw in s for kw in ["notes", "notizen", "comments", "comment", "notiz"]):
        # Extract original speaker ID by removing the note part
        original_id = re.sub(
            r"[-_\s]*(notes|notizen|comments|comment|notiz)",
            "",
            speaker_id,
            flags=re.IGNORECASE,
        ).strip()
        return "Notes", original_id
    # Map background noise variants
    elif any(
        kw in s
        for kw in [
            "background_noise",
            "hintergrundgeräusche",
            "backgroundgeräusche",
            "background",
            "hintergrund",
            "backgroundgeraeusche",
        ]
    ):
        return "BackgroundNoise", None
    # Map interviewer variants
    elif any(kw in s for kw in ["interviewer", "interviewerin"]):
        return "Interviewer", None
    # Map other special categories
    elif "mimesis" in s:
        return "Mimesis", None
    elif "external_person" in s or "freund" in s:
        return "External_person", None
    # Return original if not a special category
    return speaker_id.strip().replace(" ", "_"), None


def clean_speaker_age(age):
    """
    Cleans and standardizes the age field from the metadata.
    Handles various formats and returns an integer age or None if invalid.
    """
    if not age:
        return -1
    elif "/" in age:
        age = age.split("/")[0].strip()
        return int(age)
    else:
        return int(age)
