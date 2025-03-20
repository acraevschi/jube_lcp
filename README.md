# JuBe LCP

Conversion of JuBe Corpus for submission to LiRI Corpus Platform (LCP). The corpus was downloaded from Zenodo: https://zenodo.org/records/5648157

Before running the script, make sure to have JuBe downloaded. 

Arguments:
- `--data_folder`: Path to the folder containing the source data (default: `./Datensatz/Datenerhebung_2019/`, same as in Zenodo repository). It should contain XML files, audio files and CSV file with person metadata.
- `--input_folder`: Path to the input folder where CoNLL-U files will be created (default: `./input/`).
- `--output_folder`: Path to the output folder which will later be used for upload to the LCP (default: `./output/`).
- `--limit`: (Optional) Limit the number of files to process. Potentially useful for testing. 

You can either use `jube_prep` in command line or run `python -m jube_prep`. 

Note that this script produces `meta.json`, global attribute file for person metadata and **CoNLL-U file**. The latter means that it needs to be converted to CSVs later on for the upload. 

Potentially, one could write a simple bash script that first runs this script, then does conversion and then uploads everything. 